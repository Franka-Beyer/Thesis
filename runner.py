#!/usr/bin/env python3

from openai import OpenAI
import pandas as pd
import ast
import json
import asyncio
from openai import AsyncOpenAI
import nest_asyncio
nest_asyncio.apply()
import sys
from json_repair import repair_json
import re
import json
import Levenshtein as levenshtein
import argparse

async def get_completion(messages, model="minimax/minimax-m2.5:free"):
    """
    asynchronous function, query model (default is minimax-m2.5:free) with provided messages; return model answer (plain text)
    messages: list of dicts following convention for OpenAI chats
    model: LLM to query
    """
    response = await client.chat.completions.create(
    model=model,
    messages=messages,
    extra_body={"reasoning": {"enabled": True}}
    )
    if response:
        if response.choices:
            return response.choices[0].message
        else:
            print("Got no choices?")
            get_completion(messages, model)
    else:
        print("Got no response from the model.")

def query_model(model, proof, truth_table): #modified for flexible domains
    """
    query a model, 3-step chain prompting; prompt 3 times, always adding the previous answers to the context; returns dict of model answers
    model: name of the LLM to use, string
    proof: current proof, dict
    truth_table: original file of the respective domain, pandas table
    """
    loop = asyncio.get_event_loop()
    mess=[{"role": "user", "content": message1.format(proof=proof)}]
    res1 = loop.run_until_complete(get_completion(mess, model))
    mess.append({
    "role": "assistant",
    "content": res1.content#, #commenting out the reasoning detials: keep inputs concise and qwen does not have them?
    #"reasoning_details": res1.reasoning_details  # Pass back unmodified
    })
    mess.append({"role": "user", "content": message2.format(example_proof=truth_table.iloc[1,4], #modified
        example_summary=truth_table.iloc[1,3]['summary'])})
    loop = asyncio.get_event_loop()
    res2 = loop.run_until_complete(get_completion(mess, model))
    mess.append({
    "role": "assistant",
    "content": res2.content#,
    #"reasoning_details": res2.reasoning_details  # Pass back unmodified
    })
    mess.append({"role": "user", "content": message3.format(example_target_msg=truth_table.iloc[1,3]['target_msg'])})
    loop = asyncio.get_event_loop()
    res3 = loop.run_until_complete(get_completion(mess, model))
    return {"model_answer1": res1.content, "model_answer2": res2.content, "model_answer3": res3.content}

def query_model_preliminary(model, proof): #modified for one-shot to do just the preliminary task
    """
    query a model for the preliminary task (finding errors in a proof), 0-shot prompting; returns dict of model answer
    model: name of the LLM to use, string
    proof: current proof, dict
    """
    loop = asyncio.get_event_loop()
    mess=[{"role": "user", "content": message1.format(proof=proof)}]
    res1 = loop.run_until_complete(get_completion(mess, model))
    return {"model_answer1": res1.content}

def clean_model_response(data:str):
    """
    extract a json-object from a plain text model answer and deal with common deviations from the format
    data: plain text LLM answer, string
    """
    #data = "Some string created {'Foo': '1002803', 'Bar': 'value'} string continue"
    if re.search(r'({.+})', data, re.DOTALL):
        t = re.search(r'({.+})', data, re.DOTALL).group(0).replace("'", '"')
        dict_object = json.loads(repair_json(t))
        if type(dict_object) is dict:
            if len(dict_object.keys()) == 1: #updated to deal with json that includes {step:{conclusion...}}
                key = [e for e in dict_object.keys()][0]
                dict_object = dict_object[key]
            if isinstance(dict_object, list): #trying to fix extraction fail where cleaned response is list of list(s)
                dict_object = dict_object[0]
        return {"cleaned_response": [dict_object]}
    else:
        return None

def check_extraction(errors, response):
    """
    compare model answer to gold standard by computing edit distance (the lower the better) and similarity ratio (the higher the better) with the levenshtein library;
    returns a dict containing both values
    errors: cell in pandas table that contains the gold standard truth
    response: cell in table with the cleaned model response
    """
    edit_distance = levenshtein.distance(str(errors), str(response))
    similarity_ratio = levenshtein.ratio(str(errors), str(response))
    return {"edit_dist": edit_distance, "sim_ratio": similarity_ratio}

def unfold_cleaned_response(cell):
    if cell:
        return cell['cleaned_response']

def hallucination_check(corr, clean):
    """
    check for hallucinated model answers; true if the model response is not taken from the corrupt proof, else false
    corr: corrupt proof, dict
    clean: cleaned model response, list of dict
    """
    if clean and clean[0] not in corr['inferences']:
        return {"hallucinated": True}
    else:
        return {"hallucinated": False}

def preliminary_task(data, model:str, proof_col:int, error_col:int, file:str): #setup for preliminary task only
    """
    run the preliminary task on one set of corrupt proofs with one model and one set of prompts; produces model response files and displays some statistics
    data: update: the table with the proofs
    model: which model to use, string
    proof_col: index of the column (in a pandas table) containing the corrupt proofs
    error_col: index of the column containing the gold standard answer (the one step(s) with the error(s) from that proof)
    file: name of the file to contain the resulting models answers
    """
    proofs = []
    error_steps = []
    response1 = []
    print("XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
    #f = open("model_responses_backup.txt", "w")
    table_len = len(data)-1 #adjusted for all domains
    for row in range(0,table_len): #adjusted for drone: goes from 0 to 48
        current_proof = data.iloc[row,proof_col] #getting the rows and columns right ... 
        proofs.append(current_proof)
        current_errors = data.iloc[row,error_col] #set up for missing premise
        error_steps.append(current_errors)
        try:
            result = query_model_preliminary(model, current_proof) #adjusted for flexible models
        except:
            result = query_model_preliminary(model, current_proof)
        response1.append(result['model_answer1'])
        sys.stdout.write("X")  
        sys.stdout.flush()
        print(result['model_answer1'], file=f)
    sys.stdout.write(" [DONE]\n")
    #f.close()
    dt = {"corrupt_proof": proofs, "error_steps": error_steps, "model_response": response1}
    df = pd.DataFrame.from_dict(dt, orient='index')
    df = df.transpose()
    ###apply to dataframe and add results as new column: extract the json object from the model response
    applied_df_1 = df.apply(lambda row: clean_model_response(row.model_response), axis='columns', result_type='expand')
    new_df_1 = pd.concat([df, applied_df_1], axis='columns')
    #count how many model responses were not formatted properly (extraction failed)
    try:
        fails = new_df_1.cleaned_response.isna().sum()
        print(fails)
        ###apply to dataframe and add results as new column: compute similarity measures
        applied_df_2 = new_df_1.apply(lambda row: check_extraction(row.error_steps, row.cleaned_response), axis='columns', result_type='expand')
        new_df_2 = pd.concat([new_df_1, applied_df_2], axis='columns')
        ###apply to dataframe and add results as new column: check if answer was hallucination
        applied_check_1 = new_df_2.apply(lambda row: hallucination_check(row.corrupt_proof, row.cleaned_response), axis='columns', result_type='expand')
        new_check_1 = pd.concat([new_df_2, applied_check_1], axis='columns')
        print(new_check_1.hallucinated.value_counts())
        ###saving to file
        with open(file, "w") as f:
            f.write(new_check_1.to_json(orient='records',lines=True, force_ascii=False))
        return df
    except AttributeError:
        print("Weird things going on with the column for the cleaned response.") #now trying to save the results
        ###saving to file
        file2 = "backup" + file
        with open(file2, "w") as f:
            f.write(df.to_json(orient='records',lines=True, force_ascii=False))
        #trying to fix this
        new_df_1.rename(columns={0:"cleaned_response"}, inplace=True)
        applied_df_1_1 = new_df_1.apply(lambda row: unfold_cleaned_response(row.cleaned_response), axis='columns', result_type='expand')
        new_df_1_1 = pd.concat([df, applied_df_1_1], axis='columns')
        new_df_1_1.rename(columns={0:"cleaned_response"}, inplace=True)
        new_df_1 = new_df_1_1
        #return df
    ###apply to dataframe and add results as new column: compute similarity measures
    applied_df_2 = new_df_1.apply(lambda row: check_extraction(row.error_steps, row.cleaned_response), axis='columns', result_type='expand')
    new_df_2 = pd.concat([new_df_1, applied_df_2], axis='columns')
    ###apply to dataframe and add results as new column: check if answer was hallucination
    applied_check_1 = new_df_2.apply(lambda row: hallucination_check(row.corrupt_proof, row.cleaned_response), axis='columns', result_type='expand')
    new_check_1 = pd.concat([new_df_2, applied_check_1], axis='columns')
    print(new_check_1.hallucinated.value_counts())
    ###saving to file
    with open(file, "w") as f:
        f.write(new_check_1.to_json(orient='records',lines=True, force_ascii=False))
    return df

if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument('-d', '--domain', help='Which domain to use. cell, food, drone.')
    parser.add_argument('-t', '--task', help='Which task to complete. preliminary, typos.')
    parser.add_argument('-p', '--prompt', help='Which prompt to use.')
    parser.add_argument('-m', '--model', help='Which model to query.')
    parser.add_argument('-i', '--run_index', help='At which index to start the runs. 1, 6.')

    args = parser.parse_args()
    print(args.domain, args.task, args.prompt, args.model, args.run_index)

    #actual client to use: big Mac with Mayank
    #client = AsyncOpenAI(base_url = 'https://07e1-134-96-104-205.ngrok-free.app/v1', api_key='ollama')
    client = AsyncOpenAI(base_url='https://8dc7-134-96-104-205.ngrok-free.app/v1', api_key="ollama")

    if args.task == "preliminary" and args.domain == "cell":
        data_corrupt = pd.read_json("cell_modified_errors_listed.jsonl", lines=True)
        data = pd.read_json("cell_human.jsonl", lines=True)
    if args.task == "preliminary" and args.domain == "food":
        data_corrupt = pd.read_json("food_modified_errors_listed.jsonl", lines=True)
        data = pd.read_json("food_human.jsonl", lines=True)
    if args.task == "preliminary" and args.domain == "drone":
        data_corrupt = pd.read_json("drone_modified_errors_listed.jsonl", lines=True)
        data = pd.read_json("drone_human.jsonl", lines=True)

    if args.task == "typos" and args.domain == "cell":
        data_corrupt = pd.read_json("cell_modified_typos_listed.jsonl", lines=True)
    if args.task == "typos" and args.domain == "food":
        data_corrupt = pd.read_json("food_modified_typos_listed.jsonl", lines=True)
    if args.task == "typos" and args.domain == "drone":
        data_corrupt = pd.read_json("drone_modified_typos_listed.jsonl", lines=True)

    ###setting up the prompt templates: modified first task: search for a mistake
    if args.prompt == "testrun":
        message1 = """
    ### TASK - 1 ###
    One of the steps in the following proof contains a mistake. Find that step and pull it
    verbatim from the proof below, including conclusion, rule name, and premises.

    {proof}
    """
    if args.prompt == "testrun2":
        message1 = """
    ### TASK - 1 ###
    One of the steps in the following proof is wrong. The step itself might contain as mistake, such as a typo,
    an unproven premise or an unrelated premise, or the entire step might be unrelated to the proof.
    Find that step and quote it verbatim from the proof below, including conclusion, rule name, and premises.
    Make sure to follow proper json formatting while quoting.

    {proof}
    """

    run_ind = args.run_index
    print(message1)
    for i,j in zip(range(0, 9, 2), range(1, 10, 2)): #0,1
        print(i)
        print(j)
        #file = "food_preliminary_qwen3-6:35b_run" + str(run_ind) + ".jsonl"
        file = str(args.domain) + "_" + str(args.task) + "_" + str(args.model) + "_run" + str(run_ind) + ".jsonl"
        print(file)
        df = preliminary_task(data_corrupt, args.model, i, j, file)
        run_ind += 1

