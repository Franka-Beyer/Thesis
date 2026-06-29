#!/usr/bin/env python3

from openai import AsyncOpenAI
import pandas as pd
import ast
import json
import asyncio
import nest_asyncio
nest_asyncio.apply()
import sys
from json_repair import repair_json
import re
import Levenshtein as levenshtein
import argparse
import os

# Global client placeholder
client = None

async def get_completion(messages, model, temperature, top_p):
    """
    Asynchronous function to query the local vLLM server with provided messages.
    Handles tool calls safely and isolates conversational outputs from internal thinking tokens.
    """
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=24000
        )
        
        if response and response.choices:
            choice_msg = response.choices[0].message
            
            # Robust Tool Call Parsing
            if getattr(choice_msg, 'tool_calls', None):
                print("\n[TOOL CALL DETECTED] Model triggered functional tool calls.")
                tool_data = []
                for tool in choice_msg.tool_calls:
                    tool_data.append({
                        "id": tool.id,
                        "type": tool.type,
                        "function": {
                            "name": tool.function.name,
                            "arguments": tool.function.arguments
                        }
                    })
                choice_msg.content = json.dumps({"tool_calls_triggered": tool_data})
                return choice_msg

            # Internal Reasoning Extraction (prevents pollution of metrics)
            if hasattr(choice_msg, 'reasoning_content') and choice_msg.reasoning_content:
                print(f"\n[THINKING TRACE] Length: {len(choice_msg.reasoning_content)} chars.")
                
            return choice_msg
        else:
            print("Got no choices from the vLLM completion engine.")
            return None
    except Exception as e:
        print(f"Error encountered during API connection lifecycle: {str(e)}")
        return None

def query_model(model, proof, truth_table, temp, top_p):
    """
    Query a model, 3 step chain prompting.
    """
    loop = asyncio.get_event_loop()
    mess=[{"role": "user", "content": message1.format(proof=proof)}]
    res1 = loop.run_until_complete(get_completion(mess, model, temp, top_p))
    if not res1: return {"model_answer1": "", "model_answer2": "", "model_answer3": ""}
    
    mess.append({"role": "assistant", "content": res1.content})
    mess.append({
        "role": "user", 
        "content": message2.format(
            example_proof=truth_table.iloc[1,4], 
            example_summary=truth_table.iloc[1,3]['summary']
        )
    })
    
    res2 = loop.run_until_complete(get_completion(mess, model, temp, top_p))
    if not res2: return {"model_answer1": res1.content, "model_answer2": "", "model_answer3": ""}
    
    mess.append({"role": "assistant", "content": res2.content})
    mess.append({"role": "user", "content": message3.format(example_target_msg=truth_table.iloc[1,3]['target_msg'])})
    
    res3 = loop.run_until_complete(get_completion(mess, model, temp, top_p))
    res3_content = res3.content if res3 else ""
    return {"model_answer1": res1.content, "model_answer2": res2.content, "model_answer3": res3_content}

def query_model_preliminary(model, proof, temp, top_p):
    """
    Query a model for the preliminary task, 0 shot prompting.
    """
    loop = asyncio.get_event_loop()
    mess=[{"role": "user", "content": message1.format(proof=proof)}]
    res1 = loop.run_until_complete(get_completion(mess, model, temp, top_p))
    content = res1.content if res1 else ""
    return {"model_answer1": content}

def clean_model_response(data:str):
    """
    Extract a json object from a plain text model answer.
    """
    if not data:
        return None
    if re.search(r'({.+})', data, re.DOTALL):
        t = re.search(r'({.+})', data, re.DOTALL).group(0).replace("'", '"')
        try:
            dict_object = json.loads(repair_json(t))
            if type(dict_object) is dict:
                if len(dict_object.keys()) == 1:
                    key = [e for e in dict_object.keys()][0]
                    dict_object = dict_object[key]
            if isinstance(dict_object, list): #trying to fix extraction fail where cleaned_response is a list of list(s)
                dict_object = dict_object[0]
            return {"cleaned_response": [dict_object]}
        except Exception:
            return None
    else:
        return None

def check_extraction(errors, response):
    """
    Compare model answer to gold standard by computing edit distance.
    """
    edit_distance = levenshtein.distance(str(errors), str(response))
    similarity_ratio = levenshtein.ratio(str(errors), str(response))
    return {"edit_dist": edit_distance, "sim_ratio": similarity_ratio}

def unfold_cleaned_response(cell):
    if cell:
        return cell['cleaned_response']

def hallucination_check(corr, clean):
    """
    Check for hallucinated model answers.
    """
    if clean and isinstance(clean, list) and len(clean) > 0:
        if clean[0] not in corr.get('inferences', []):
            return {"hallucinated": True}
    return {"hallucinated": False}

def preliminary_task(data, model:str, proof_col:int, error_col:int, file:str, temp:float, top_p:float):
    """
    Run the preliminary task on one set of corrupt proofs.
    """
    proofs = []
    error_steps = []
    response1 = []
    print("XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
    
    table_len = len(data)
    for row in range(0, table_len):
        current_proof = data.iloc[row, proof_col]
        proofs.append(current_proof)
        current_errors = data.iloc[row, error_col]
        error_steps.append(current_errors)
        
        try:
            result = query_model_preliminary(model, current_proof, temp, top_p)
        except Exception:
            try:
                result = query_model_preliminary(model, current_proof, temp, top_p)
            except Exception:
                result = {"model_answer1": ""}
                
        # FIXED INDENTATION: Always append regardless of exceptions
        response1.append(result['model_answer1'])
        #sys.stdout.write("X")  
        sys.stdout.flush()
            
    sys.stdout.write(" [DONE]\n")
    
    dt = {"corrupt_proof": proofs, "error_steps": error_steps, "model_response": response1}
    df = pd.DataFrame.from_dict(dt, orient='index').transpose()
    
    applied_df_1 = df.apply(lambda row: clean_model_response(row.model_response), axis='columns', result_type='expand')
    new_df_1 = pd.concat([df, applied_df_1], axis='columns')
    
    try:
        if "cleaned_response" not in new_df_1.columns or new_df_1["cleaned_response"].isna().all():
            raise AttributeError
            
        fails = new_df_1.cleaned_response.isna().sum()
        print(f"Extraction failed cases: {fails}")
        
        applied_df_2 = new_df_1.apply(lambda row: check_extraction(row.error_steps, row.cleaned_response), axis='columns', result_type='expand')
        new_df_2 = pd.concat([new_df_1, applied_df_2], axis='columns')
        
        applied_check_1 = new_df_2.apply(lambda row: hallucination_check(row.corrupt_proof, row.cleaned_response), axis='columns', result_type='expand')
        new_check_1 = pd.concat([new_df_2, applied_check_1], axis='columns')
        
        with open(file, "w") as f:
            f.write(new_check_1.to_json(orient='records', lines=True, force_ascii=False))
        return df
    except AttributeError:
        print("Handling response variations via safe column transformation loops.")
        file2 = os.path.join(os.path.dirname(file), "backup_" + os.path.basename(file))
        with open(file2, "w") as f:
            f.write(df.to_json(orient='records', lines=True, force_ascii=False))
            
        if 0 in new_df_1.columns:
            new_df_1.rename(columns={0: "cleaned_response"}, inplace=True)
            
        # Using .get() to prevent KeyError crashes
        applied_df_1_1 = new_df_1.apply(lambda row: unfold_cleaned_response(row.get("cleaned_response")), axis='columns', result_type='expand')
        new_df_1_1 = pd.concat([df, applied_df_1_1], axis='columns')
        
        if 0 in new_df_1_1.columns:
            new_df_1_1.rename(columns={0: "cleaned_response"}, inplace=True)
        new_df_1 = new_df_1_1

    applied_df_2 = new_df_1.apply(lambda row: check_extraction(row.error_steps, row.get("cleaned_response")), axis='columns', result_type='expand')
    new_df_2 = pd.concat([new_df_1, applied_df_2], axis='columns')
    
    applied_check_1 = new_df_2.apply(lambda row: hallucination_check(row.corrupt_proof, row.get("cleaned_response")), axis='columns', result_type='expand')
    new_check_1 = pd.concat([new_df_2, applied_check_1], axis='columns')
    
    with open(file, "w") as f:
        f.write(new_check_1.to_json(orient='records', lines=True, force_ascii=False))
    return df

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--domain', help='Which domain to use. cell, food, drone.')
    parser.add_argument('-t', '--task', help='Which task to complete. preliminary, typos.')
    parser.add_argument('-p', '--prompt', help='Which prompt to use.')
    parser.add_argument('-m', '--model', help='Which model to query.')
    # Fixed run_index to be parsed as integer
    parser.add_argument('-i', '--run_index', type=int, default=1, help='At which index to start the runs.')
    parser.add_argument('--port', type=int, default=8093, help='Port of the local vLLM server.')
    parser.add_argument('--temperature', type=float, default=0.7, help='Generation temperature parameter.')
    parser.add_argument('--top_p', type=float, default=0.9, help='Generation top_p sampling parameter.')
    parser.add_argument('--output_dir', type=str, default="/home/frbe00002/results", help='Directory where output metrics should be saved.')
    
    args = parser.parse_args()

    # Pre create directory
    os.makedirs(args.output_dir, exist_ok=True)

    client = AsyncOpenAI(
        base_url=f'http://0.0.0.0:{args.port}/v1',
        api_key='dummy'
    )

    if args.task == "preliminary" and args.domain == "cell":
        data_corrupt = pd.read_json("cell_modified_errors_listed.jsonl", lines=True)
    elif args.task == "preliminary" and args.domain == "food":
        data_corrupt = pd.read_json("food_modified_errors_listed.jsonl", lines=True)
    elif args.task == "preliminary" and args.domain == "drone":
        data_corrupt = pd.read_json("drone_modified_errors_listed.jsonl", lines=True)

    if args.task == "typos" and args.domain == "cell":
        data_corrupt = pd.read_json("cell_modified_typos_listed.jsonl", lines=True)
    elif args.task == "typos" and args.domain == "food":
        data_corrupt = pd.read_json("food_modified_typos_listed.jsonl", lines=True)
    elif args.task == "typos" and args.domain == "drone":
        data_corrupt = pd.read_json("drone_modified_typos_listed.jsonl", lines=True)

    global message1, message2, message3
    if args.prompt == "testrun":
        message1 = "### TASK 1 ###\nOne of the steps in the following proof contains a mistake. Find that step and pull it\nverbatim from the proof below, including conclusion, rule name, and premises.\n\n{proof}"
    elif args.prompt == "testrun2":
        message1 = "### TASK 1 ###\nOne of the steps in the following proof is wrong. The step itself might contain as mistake, such as a typo,\nan unproven premise or an unrelated premise, or the entire step might be unrelated to the proof.\nFind that step and quote it verbatim from the proof below, including conclusion, rule name, and premises.\nMake sure to follow proper json formatting while quoting.\n\n{proof}"

    run_ind = args.run_index
    for i, j in zip(range(0, 9, 2), range(1, 10, 2)):
        # Extract base model name safely so it does not create bad directory paths
        clean_model_name = args.model.split('/')[-1]
        filename = f"{args.domain}_{args.task}_{clean_model_name}_run{run_ind}.jsonl"
        
        full_save_path = os.path.join(args.output_dir, filename)
        if os.path.exists(full_save_path):
            run_ind += 1
            print(f"Skipping existing file: {full_save_path}")
            continue
        print(f"Launching evaluation iteration writing to: {full_save_path}")
        df = preliminary_task(data_corrupt, args.model, i, j, full_save_path, args.temperature, args.top_p)
        run_ind += 1
