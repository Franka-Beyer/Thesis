#!/usr/bin/env python3

import json
import pandas as pd
from random import randrange
from copy import deepcopy
import random
import argparse

def inf2ind_dict(data): #helper function: produce dict for inference steps to index in original proof
    """
    take one proof (dict) and produce a dict that assigns to each inference step in this proof the index at which it occurs
    data: proof (dict), containing all steps under the key 'inferences'
    """
    d = {}
    for i, e in enumerate(data['inferences']):
        d[str(e)] = i
    return d

def sort_by_rule(data): #helper function: produce dict sorted by rule applied, contains lists of steps
    """
    take one proof (dict) and produce a dict that uses all rules occuring as keys with lists of the respective steps as values
    data: proof (dict), containing all steps under the key 'inferences'
    """
    inferences_by_rule = {}
    for inference in data['inferences']:
        rule = inference['ruleName'] 
        if rule not in inferences_by_rule.keys():
            inferences_by_rule[rule] = [inference]
        else:
            inferences_by_rule[rule].append(inference)
    return inferences_by_rule

def sort_steplist_by_rule(steplist): #helper function: produce dict sorted by rule applied, contains lists of steps
    """
    take one list of inference steps and produce a dict that uses all rules occuring as keys with lists of the respective steps as values
    steplist: list of inference steps from one or more proofs (should be from the same domain and thus use the same rules for the result to make sense)
    """
    inferences_by_rule = {}
    for inference in steplist:
        rule = inference['ruleName'] 
        if rule not in inferences_by_rule.keys():
            inferences_by_rule[rule] = [inference]
        else:
            inferences_by_rule[rule].append(inference)
    return inferences_by_rule

def get_multi_premise_steps(data, n=2): #helper function: produce list of all steps with >= n premises
    """
    takes one proof and produces a list of all inference steps that use >= n premises to derive their conclusion
    data: proof (dict), containing all steps under the key 'inferences'
    n: minimum number of premises all steps in the result are to contain, default set to 2
    """
    cans = []
    for step in data['inferences']:
        if len(step['premises']) >= n:
            cans.append(step)
    return cans

def find_premise_conclusion_mismatch(corrupt_proof): #needs to be the actual proof itself, not the dict
    """
    find all steps in a proof that use premises that were never conclusions (of other steps) and are thus unproven, produces a list of the steps that use unproven preimises
    corrupt_proof: proof (dict), containing all steps under the key 'inferences'
    """
    conclusions_c = []
    extract_conclusions(corrupt_proof, conclusions_c)
    res = []
    for step in corrupt_proof['inferences']:
        if len(step['premises']) == 0:
            continue
        elif len(step['premises']) == 1:
            if step['premises'][0] not in conclusions_c:
                res.append(step)
        elif len(step['premises']) > 1:
            for prem in step['premises']:
                if prem not in conclusions_c:
                    res.append(step)
    return res

def extract_steps(data, steps = []): #helper function: add all steps from a proof to existing list
    """
    append all steps taken in a proof to an existing (or new) list
    data: proof (dict), containing all steps under the key 'inferences'
    steps: list the steps are to be appended to, default set to empty list
    """
    for step in data['inferences']:
        if step not in steps:
            steps.append(step)

            
def extract_premises(data, premises = []): #helper function: add all premises from a proof to existing list
    """
    append all previously unseen premises used in a proof to an existing (or new) list
    data: proof (dict), containing all steps under the key 'inferences'
    premises: list the premises are to be appended to, default set to empty list
    """
    for step in data['inferences']:
        if len(step['premises']) == 0:
            continue
        if len(step['premises']) == 1:
            if step['premises'][0] not in premises:
                premises.append(step['premises'][0])
        if len(step['premises']) > 1:
            for prem in step['premises']:
                if prem not in premises:
                    premises.append(prem)
                    
def extract_conclusions(data, conclusions = []): #helper function: add all conclusions from a proof to existing list
    """
    append all previously unseen conclusions from a proof to an existing (or new) list
    data: proof (dict), containing all steps under the key 'inferences'
    conclusions: list the conclusions are to be appended to, default set to empty list
    """
    for step in data['inferences']:
        if step['conclusion'] not in conclusions:
            conclusions.append(step['conclusion'])


def remove_random_steps_of_rule_new(data, rule:str, number:int):
    """
    from one proof remove a specific number of steps that apply a specific rule, returns a dict (to produce new pandas columns) containing the now corrupted proof and a list of all steps that now contain unproven premises and thus mistakes
    data: proof (dict), containing all steps under the key 'inferences'
    rule: name of the rule
    number: number of steps to remove in total
    """
    sorted_rules = sort_by_rule(data)
    res = deepcopy(data)
    if rule=="Asserted Conclusion" and "asserted" in sorted_rules.keys(): #modified for food
        rule = "asserted"
    if rule=="Asserted Conclusion" and "Asserted" in sorted_rules.keys(): #modified for drone
        rule = "Asserted"
    if rule in sorted_rules.keys():
        candidates = []
        for e in range(number):
            ran = len(sorted_rules[rule])
            index = randrange(ran)
            try:
                cand = sorted_rules[rule].pop(index)
                candidates.append(cand)
            except IndexError:
                print("index trouble: index " + str(index))
        for c in candidates:
            res['inferences'].remove(c)
    else:
        print("Error: no occurence of " + rule + " in proof.") #update: now returns list of weird steps
    if rule=="asserted":
        rule = "Asserted Conclusion"
    if rule=="Asserted":
        rule = "Asserted Conclusion"
    return {'proof_missing_' + str(number) + '_' + rule: res, "steps_unproven_premises": find_premise_conclusion_mismatch(res)}

def remove_random_premises(data, number:int, n=2):
    """
    from one proof remove 1 premise from a certain number of steps that have >= n premises, returns a dict containing the now corrupted proof and a list of the steps that miss premises
    data: proof (dict), containing all steps under the key 'inferences'
    number: number of steps whose premises are to be removed
    n: number of premises the steps to be corrupted are to have originally, default set to 2
    """
    res = deepcopy(data)
    candidates = get_multi_premise_steps(data, n=n)
    if not candidates:
        print('No step with >= n premises. n = ' + str(n))
        return None
    backup = deepcopy(candidates) #ensure original proof stays whole
    cs = []
    indices = random.sample(range(0, len(candidates)), number)
    for i in indices:
        cand = backup[i]['premises'].pop(randrange(n))
        cs.append(cand)
    modified_steps = [] #trying to keep a list of the steps modified
    for i,c in zip(indices, cs):
        step_ind = res['inferences'].index(candidates[i])
        res['inferences'][step_ind]['premises'].remove(c)
        modified_steps.append(res['inferences'][step_ind])
    return {'proof_missing_1_premise_in_' + str(number) + '_steps_of_>=_' + str(n) + '_premises': res, "steps_missing_premises": modified_steps}

def insert_steps(data, all_steps, n=1, rule=None): #add n random false steps (of certain cat) to a given proof
    """
    into one proof insert n new steps (of a specified rule if given) from a list of possible candidates, returns a dict containing the now corrupted proof and a list of the added steps
    data: proof (dict), containing all steps under the key 'inferences
    all_steps: list of all possible candidate steps (usually a list of all steps from the domain)
    n: number of steps to add, default set to 1
    rule: name of the rule the inserted steps are to apply, default set to None
    """
    current_steps = []
    res = deepcopy(data)
    extract_steps(data, current_steps)
    x = 0
    modified_steps = [] #trying to keep list of errors introduced
    if rule:
        lookup = sort_steplist_by_rule(all_steps)
        if rule=="Asserted Conclusion" and "asserted" in lookup.keys(): #modified for food
            rule = "asserted"
        if rule=="Asserted Conclusion" and "Asserted" in lookup.keys(): #modified for drone
            rule = "Asserted"
        while x < n:
            candidate = random.sample(lookup[rule], 1)[0]
            if candidate not in current_steps:
                res['inferences'].insert(random.sample(range(0, len(current_steps)), 1)[0], candidate)
                modified_steps.append(candidate)
                x += 1
        if rule=="asserted":
            rule = "Asserted Conclusion"
        if rule=="Asserted":
            rule = "Asserted Conclusion"
        return {'proof_with_' + str(n) + '_additional_random_' + rule: res, "errors": modified_steps}
    else:
        while x < n:
            candidate = random.sample(all_steps, 1)[0]
            if candidate not in current_steps:
                res['inferences'].insert(random.sample(range(0, len(current_steps)), 1)[0], candidate)
                modified_steps.append(candidate)
                x += 1
        return {'proof_with_' + str(n) + '_additional_random_steps': res, "false_steps": modified_steps}

def insert_premises(data, all_premises, n=1, rule=None, n2=1): #add n random false premises (to n2 steps of certain cat) to a given proof
    """
    in one proof insert n unrelated premises into n2 steps (of a specific category), produces a dict containing the corrupted proof and a list of the steps with the false premises
    data: proof (dict), containing all steps under the key 'inferences
    all_premises: list of all possible candidate premises, usually a list of all premises used within the domain
    n: number of premises to be inserted into each step, default set to 1
    rule: name of the rule the steps that are to be corrupted are to apply, default set to None
    n2: number of steps that are to be corrupted, default set to 1
    """
    current_steps = []
    res = deepcopy(data)
    x = 0
    y = 0
    lookup = sort_by_rule(data)
    modified_steps = [] #trying to keep list of errors introduced
    if rule=="Asserted Conclusion" and "asserted" in lookup.keys(): #trying to get rid of extra column
        rule = "asserted"
    if rule=="Asserted Conclusion" and "Asserted" in lookup.keys(): #trying to get rid of extra column
        rule = "Asserted"
    if rule and rule in lookup.keys(): #modified: trying to make sure that the proofs contain the rule
        #lookup = sort_by_rule(data)
        while x < n2:
            candidate = random.sample(lookup[rule], 1)[0]
            if candidate in data['inferences']:
                step_index = data['inferences'].index(candidate)
                current_premises = data['inferences'][step_index]['premises']
                while y < n:
                    candidate_prem = random.sample(all_premises, 1)[0]
                    if candidate_prem not in current_premises:
                        if len(current_premises) == 0:
                            res['inferences'][step_index]['premises'].append(candidate_prem)
                        else:
                            res['inferences'][step_index]['premises'].insert(random.sample(range(0, len(current_premises)), 1)[0], candidate_prem)
                        y += 1
                        modified_steps.append(res['inferences'][step_index])
            x += 1
        if rule=="asserted":
            rule = "Asserted Conclusion"
        if rule=="Asserted":
            rule = "Asserted Conclusion"
        return {'proof_with_' + str(n) + '_additional_random_premises_in_' + str(n2) + '_' + rule: res, "steps_false_premises": modified_steps}
    else:
        while x < n2:
            candidate = random.sample(data['inferences'], 1)[0]
            step_index = data['inferences'].index(candidate)
            current_premises = data['inferences'][step_index]['premises']
            while y < n:
                candidate_prem = random.sample(all_premises, 1)[0]
                if candidate_prem not in current_premises:
                    if len(current_premises) == 0:
                        res['inferences'][step_index]['premises'].append(candidate_prem)
                    else:
                        res['inferences'][step_index]['premises'].insert(random.sample(range(0, len(current_premises)), 1)[0], candidate_prem)
                    y += 1
                    modified_steps.append(res['inferences'][step_index])
                x += 1
        return {'proof_with_' + str(n) + '_additional_random_premises_in_' + str(n2) + '_random_steps': res, "steps_false_premises": modified_steps}

def add_typo(data, n, w, wh='conclusion', typo="rem_w", cont=False): #only for conclusions or ruleNames
    """
    in one proof introduce n typos (of a certain kind) in w steps that apply a specific rule, either continuous or not, produces dict containing the now corrupted proof and a list of the step(s) containing the typos
    data: proof (dict), containing all steps under the key 'inferences'
    n: number of typos per step
    w: number of steps to be affected
    wh: key specifying which part of the step is to be affected; 'conclusion', 'ruleName', or 'premises'
    typo: variable specifying what kind of typo is to be introduced; 'rem_w' to remove entire words, 'rem_l' to remove (spans of) letters from random words
    cont: whether letters are to be removed in continuous spans (True) or randomly chosen (False)
    """
    x = 0
    res = deepcopy(data)
    steps = []
    modified_steps = [] #trying to keep list of modified steps
    while x < w: #work on w steps
        step_ind = random.sample(range(0,len(data['inferences'])),1)[0]
        if step_ind in steps: #make sure we get w different steps
            continue
        else:
            steps.append(step_ind)
        y = 0
        while y < n: #do n things
            st = res['inferences'][step_ind][wh]
            #print(st)
            if typo == "rem_w": #remove a word
                #print(st.split())
                if len(st.split()) == 1:
                    spli = [e for e in re.split(r'(\W)', st) if e != '']
                w_ind = random.sample(range(0,len(spli)),1)[0] #adjusted to deal with error
                l = [e for e in re.split(r'(\W)', res['inferences'][step_ind][wh]) if e != '']
                if cont and n>1: #adjusted to be able to remove spans of words
                    nd_ind = w_ind + n
                    if len(l) < nd_ind:
                        del l[-nd_ind:]
                    else:
                        del l[w_ind:nd_ind]
                    y = n
                else:
                    del l[w_ind]
                if len(st.split()) == 1:
                    res['inferences'][step_ind][wh] = "".join(l)
                else:
                    res['inferences'][step_ind][wh] = " ".join(l)
            if typo == "rem_l": #remove a letter
                w_ind = random.sample(range(0,len(st.split())),1)[0]
                l = res['inferences'][step_ind][wh].split()
                l_ind = random.sample(range(0,len(l[w_ind])),1)[0]
                ls = list(l[w_ind])
                if cont and n>1: #adjusted to produce typos where spans of letters are missing if needed
                    nd_ind = l_ind + n
                    if len(ls) < nd_ind:
                        del ls[-nd_ind:] #adjusted to deal with indices out of bounds
                    else:
                        del ls[l_ind:nd_ind]
                    y = n #adjusted for easier logic
                else:
                    del ls[l_ind]
                l[w_ind] = "".join(ls)
                res['inferences'][step_ind][wh] = " ".join(l)
            if typo == "dup_l" or typo == "ins_l": #joined condition due to overlap
                w_ind = random.sample(range(0,len(st.split())),1)[0]
                l = res['inferences'][step_ind][wh].split()
                l_ind = random.sample(range(0,len(l[w_ind])),1)[0]
                ls = list(l[w_ind])
                if typo == "dup_l":
                    dup = ls[l_ind]
                if typo == "ins_l":
                    dup = random.choice(string.ascii_letters)
                if cont and n>1:
                    for _ in range(n):
                        ls.insert(l_ind, dup)
                    y = n
                else:
                    ls.insert(l_ind, dup)
                l[w_ind] = "".join(ls)
                res['inferences'][step_ind][wh] = " ".join(l)
            if typo == "scr_l" and n >= 2:
                w_ind = random.sample(range(0,len(st.split())),1)[0]
                l = res['inferences'][step_ind][wh].split()
                l_ind = random.sample(range(0,len(l[w_ind])),1)[0]
                ls = list(l[w_ind])
                if cont:
                    while ls == list(l[w_ind]): #enforcing noticable change
                        nd_ind = l_ind + n
                        if len(ls) < nd_ind:
                            copy = ls[-nd_ind:]
                            random.shuffle(copy)
                            ls[-nd_ind:] = copy #overwriting with shuffled slice
                        else:
                            copy = ls[l_ind:nd_ind]
                            random.shuffle(copy)
                            ls[l_ind:nd_ind] = copy
                    y = n
                else:
                    l_inds = random.sample(range(0,len(l[w_ind])),2) #sampling a list
                    ls[l_inds[0]], ls[l_inds[1]] = ls[l_inds[1]], ls[l_inds[0]]
                    y += 1 #trying to have the input parameters make sense in this context
                l[w_ind] = "".join(ls)
                res['inferences'][step_ind][wh] = " ".join(l)
            y += 1
        modified_steps.append(res['inferences'][step_ind]) #adjusted to get correct output
        x += 1
    return {'proof_typoed_' + typo + '_' + str(n) + '_time(s)_in_' + str(w) +'_'+ wh + 's': res, "steps_typoed": modified_steps}


if __name__ == "__main__":

    parser = argparse.ArgumentParser(prog='Corrupter', description='The orignial notebook condensed as a python script.')
    parser.add_argument('-d', '--domain', help='Which domain to use. cell, food, or drone. all for all of them.')
    parser.add_argument('-c', '--corruption', help='Which type of corruption to use. del_step, del_prem, add_step, add_prem, add_typo. full for all of them.')
    parser.add_argument('-t', '--typo', default=False, help='Whether the typo variations are to be computed or not.')
    parser.add_argument('-s', '--sort_of_typo', default=None, help='What sort of typo to produce. rem_w, rem_l, dup_l, ins_l, scr_l.')
    parser.add_argument('-f', '--store_file', default=False, help='Whether to store the results in a file or not. For name check script.')

    args = parser.parse_args()
    print(args.domain, args.corruption, args.typo, args.sort_of_typo, args.store_file)

    a = False
    if args.domain == "all":
        a = True

    b = False
    if args.domain == "full":
        b = True

    if args.domain == "cell" or a:
        cell = pd.read_json("cell_human.jsonl", lines=True)
        print("c")
    if args.domain == "food" or a:
        food = pd.read_json("food_human.jsonl", lines=True)
        print("f")
    if args.domain == "drone" or a:
        drone = pd.read_json("drone_human.jsonl", lines=True)
        print("d")

    if (args.domain == "cell" or a) and (args.corruption == "del_step" or b):
        ###apply to dataframe and add results as new column: delete steps of certain rule category
        applied_cell_1 = cell.apply(lambda row: remove_random_steps_of_rule_new(row.proof, 'Asserted Conclusion', 1), axis='columns', result_type='expand')
        new_cell_1 = pd.concat([cell, applied_cell_1], axis='columns')

    if (args.domain == "food" or a) and (args.corruption == "del_step" or b):
        ###apply to dataframe and add results as new column: delete steps of certain rule category
        applied_food_1 = food.apply(lambda row: remove_random_steps_of_rule_new(row.proof, 'Asserted Conclusion', 1), axis='columns', result_type='expand')
        new_food_1 = pd.concat([food, applied_food_1], axis='columns')
        #applied to food: works, modified to return steps that contain errors, dealt with asserted/Asserted Conclusion

    if (args.domain == "drone" or a) and (args.corruption == "del_step" or b):
        ###apply to dataframe and add results as new column: delete steps of certain rule category
        applied_drone_1 = drone.apply(lambda row: remove_random_steps_of_rule_new(row.proof, 'Asserted Conclusion', 1), axis='columns', result_type='expand')
        new_drone_1 = pd.concat([drone, applied_drone_1], axis='columns')
        #applied to drone: works

    if (args.domain == "cell" or a) and (args.corruption == "del_prem" or b):
        ###apply to dataframe and add results as new column: delete premises from steps with >= n premises
        applied_cell_2 = cell.apply(lambda row: remove_random_premises(row.proof, 1, n=2), axis='columns', result_type='expand')
        new_cell_2 = pd.concat([cell, applied_cell_2], axis='columns')

    if (args.domain == "food" or a) and (args.corruption == "del_prem" or b):
        ###apply to dataframe and add results as new column: delete premises from steps with >= n premises
        applied_food_2 = food.apply(lambda row: remove_random_premises(row.proof, 1, n=2), axis='columns', result_type='expand')
        new_food_2 = pd.concat([food, applied_food_2], axis='columns')
        #applied to food: seems to work just fine?, modified to also return steps that contain errors

    if (args.domain == "drone" or a) and (args.corruption == "del_prem" or b):
        ###apply to dataframe and add results as new column: delete premises from steps with >= n premises
        applied_drone_2 = drone.apply(lambda row: remove_random_premises(row.proof, 1, n=2), axis='columns', result_type='expand')
        new_drone_2 = pd.concat([drone, applied_drone_2], axis='columns')
        #applied to drone: works just fine?

    if (args.domain == "cell" or a) and (args.corruption == "add_step" or b):
        ###apply to dataframe and add results as new column: insert n random steps from same domain per proof
        all_steps = []
        cell.apply(lambda row: extract_steps(row.proof, all_steps), axis='columns', result_type='expand')
        print(len(all_steps))
        applied_cell_3 = cell.apply(lambda row: insert_steps(row.proof, all_steps, n=1, rule='Asserted Conclusion'), axis='columns', result_type='expand')
        new_cell_3 = pd.concat([cell, applied_cell_3], axis='columns')

    if (args.domain == "food" or a) and (args.corruption == "add_step" or b):
        ###apply to dataframe and add results as new column: insert n random steps from same domain per proof
        all_steps = []
        food.apply(lambda row: extract_steps(row.proof, all_steps), axis='columns', result_type='expand')
        print(len(all_steps))
        applied_food_3 = food.apply(lambda row: insert_steps(row.proof, all_steps, n=1, rule='Asserted Conclusion'), axis='columns', result_type='expand')
        new_food_3 = pd.concat([food, applied_food_3], axis='columns')
        #applied to food: seems to work just fine?, modified to also return steps that contain errors

    if (args.domain == "drone" or a) and (args.corruption == "add_step" or b):
        ###apply to dataframe and add results as new column: insert n random steps from same domain per proof
        all_steps = []
        drone.apply(lambda row: extract_steps(row.proof, all_steps), axis='columns', result_type='expand')
        print(len(all_steps))
        applied_drone_3 = drone.apply(lambda row: insert_steps(row.proof, all_steps, n=1, rule='Asserted Conclusion'), axis='columns', result_type='expand')
        new_drone_3 = pd.concat([drone, applied_drone_3], axis='columns')
        #applied to drone: works after fix for assertion names

    if (args.domain == "cell" or a) and (args.corruption == "add_prem" or b):
        ###apply to dataframe and add results as new column: insert n random premises from same domain per proof
        all_premises = []
        cell.apply(lambda row: extract_premises(row.proof, all_premises), axis='columns', result_type='expand')
        print(len(all_premises))
        applied_cell_4 = cell.apply(lambda row: insert_premises(row.proof, all_premises, n=1, rule='Asserted Conclusion'), axis='columns', result_type='expand')
        new_cell_4 = pd.concat([cell, applied_cell_4], axis='columns')

    if (args.domain == "food" or a) and (args.corruption == "add_prem" or b):
        ###apply to dataframe and add results as new column: insert n random premises from same domain per proof
        all_premises = []
        food.apply(lambda row: extract_premises(row.proof, all_premises), axis='columns', result_type='expand')
        print(len(all_premises))
        applied_food_4 = food.apply(lambda row: insert_premises(row.proof, all_premises, n=1, rule='Asserted Conclusion'), axis='columns', result_type='expand')
        new_food_4 = pd.concat([food, applied_food_4], axis='columns')
        #applied to food: error where proofs had no asserted conclusions -> now in separate cols?, modified to also return steps that contain errors

    if (args.domain == "drone" or a) and (args.corruption == "add_prem" or b):
        ###apply to dataframe and add results as new column: insert n random premises from same domain per proof
        all_premises = []
        drone.apply(lambda row: extract_premises(row.proof, all_premises), axis='columns', result_type='expand')
        print(len(all_premises))
        applied_drone_4 = drone.apply(lambda row: insert_premises(row.proof, all_premises, n=1, rule='Asserted Conclusion'), axis='columns', result_type='expand')
        new_drone_4 = pd.concat([drone, applied_drone_4], axis='columns')
        #applied to drone: works just fine

    if (args.domain == "cell" or a) and (args.corruption == "add_typo" or b):
        ###apply to dataframe and add results as new column: add n random typos in the conclusions of w steps 
        applied_cell_5 = cell.apply(lambda row: add_typo(row.proof, 1, 2, typo='rem_l'), axis='columns', result_type='expand')
        new_cell_5 = pd.concat([cell, applied_cell_5], axis='columns')

    if (args.domain == "food" or a) and (args.corruption == "add_typo" or b):
        ###apply to dataframe and add results as new column: add n random typos in the conclusions of w steps 
        applied_food_5 = food.apply(lambda row: add_typo(row.proof, 1, 2, typo='rem_l'), axis='columns', result_type='expand')
        new_food_5 = pd.concat([food, applied_food_5], axis='columns')
        #applied to food: seems to work fine, now with colum for error steps

    if (args.domain == "drone" or a) and (args.corruption == "add_typo" or b):
        ###apply to dataframe and add results as new column: add n random typos in the conclusions of w steps 
        applied_drone_5 = drone.apply(lambda row: add_typo(row.proof, 1, 2, typo='rem_l'), axis='columns', result_type='expand')
        new_drone_5 = pd.concat([drone, applied_drone_5], axis='columns')
        #applied to drone: works just fine?

    if (args.domain == "cell" or a) and b:
        new_cell = pd.concat([applied_cell_1, applied_cell_2, applied_cell_3, applied_cell_4, applied_cell_5], axis='columns')
        if args.store_file:
            ###saving to file
            with open("cell_modified_errors_listed.jsonl", "w") as f:
                f.write(new_cell.to_json(orient='records',lines=True, force_ascii=False))
    if (args.domain == "food" or a) and b:
        new_food = pd.concat([applied_food_1, applied_food_2, applied_food_3, applied_food_4, applied_food_5], axis='columns')
        if args.store_file:
            ###saving to file
            with open("food_modified_errors_listed.jsonl", "w") as f:
                f.write(new_food.to_json(orient='records',lines=True, force_ascii=False))
    if (args.domain == "drone" or a) and b:
        new_drone = pd.concat([applied_drone_1, applied_drone_2, applied_drone_3, applied_drone_4, applied_drone_5], axis='columns')
        if args.store_file:
            ###saving to file
            with open("drone_modified_errors_listed.jsonl", "w") as f:
                f.write(new_drone.to_json(orient='records',lines=True, force_ascii=False))


###Typo investigation: how many typos does it take until the models notice?
    if (args.domain == "cell" or a) and args.typo:
        ###apply to dataframe and add results as new column: add n random typos in the conclusions of w steps 
        applied_cell_6 = cell.apply(lambda row: add_typo(row.proof, 1, 1, typo=args.sort_of_typo), axis='columns', result_type='expand')
        new_cell_6 = pd.concat([cell, applied_cell_6], axis='columns')
        applied_cell_6.rename(columns={'steps_typoed': 'steps_typoed_once'}, inplace=True)
        applied_cell_7 = cell.apply(lambda row: add_typo(row.proof, 2, 1, typo=args.sort_of_typo, cont=True), axis='columns', result_type='expand')
        new_cell_7 = pd.concat([cell, applied_cell_7], axis='columns')
        applied_cell_7.rename(columns={'steps_typoed': 'steps_typoed_twice'}, inplace=True)
        applied_cell_8 = cell.apply(lambda row: add_typo(row.proof, 3, 1, typo=args.sort_of_typo, cont=True), axis='columns', result_type='expand')
        new_cell_8 = pd.concat([cell, applied_cell_8], axis='columns')
        applied_cell_8.rename(columns={'steps_typoed': 'steps_typoed_thrice'}, inplace=True)
        applied_cell_9 = cell.apply(lambda row: add_typo(row.proof, 4, 1, typo=args.sort_of_typo, cont=True), axis='columns', result_type='expand')
        new_cell_9 = pd.concat([cell, applied_cell_9], axis='columns')
        applied_cell_9.rename(columns={'steps_typoed': 'steps_typoed_fourfold'}, inplace=True)
        applied_cell_10 = cell.apply(lambda row: add_typo(row.proof, 5, 1, typo=args.sort_of_typo, cont=True), axis='columns', result_type='expand')
        new_cell_10 = pd.concat([cell, applied_cell_10], axis='columns')
        applied_cell_10.rename(columns={'steps_typoed': 'steps_typoed_fivefold'}, inplace=True)

        cell_t = pd.concat([applied_cell_6, applied_cell_7, applied_cell_8, applied_cell_9, applied_cell_10], axis='columns')

        if args.store_file:
            ###saving to file
            filename = "cell_modified_typos_" + args.sort_of_typo + ".jsonl"
            with open(filename, "w") as f:
                f.write(cell_t.to_json(orient='records',lines=True, force_ascii=False))

    if (args.domain == "food" or a) and args.typo:
        ###apply to dataframe and add results as new column: add n random typos in the conclusions of w steps 
        applied_food_6 = food.apply(lambda row: add_typo(row.proof, 1, 1, typo=args.sort_of_typo), axis='columns', result_type='expand')
        new_food_6 = pd.concat([food, applied_food_6], axis='columns')
        applied_food_6.rename(columns={'steps_typoed': 'steps_typoed_once'}, inplace=True)
        applied_food_7 = food.apply(lambda row: add_typo(row.proof, 2, 1, typo=args.sort_of_typo, cont=True), axis='columns', result_type='expand')
        new_food_7 = pd.concat([food, applied_food_7], axis='columns')
        applied_food_7.rename(columns={'steps_typoed': 'steps_typoed_twice'}, inplace=True)
        applied_food_8 = food.apply(lambda row: add_typo(row.proof, 3, 1, typo=args.sort_of_typo, cont=True), axis='columns', result_type='expand')
        new_food_8 = pd.concat([food, applied_food_8], axis='columns')
        applied_food_8.rename(columns={'steps_typoed': 'steps_typoed_thrice'}, inplace=True)
        applied_food_9 = food.apply(lambda row: add_typo(row.proof, 4, 1, typo=args.sort_of_typo, cont=True), axis='columns', result_type='expand')
        new_food_9 = pd.concat([food, applied_food_9], axis='columns')
        applied_food_9.rename(columns={'steps_typoed': 'steps_typoed_fourfold'}, inplace=True)
        applied_food_10 = food.apply(lambda row: add_typo(row.proof, 5, 1, typo=args.sort_of_typo, cont=True), axis='columns', result_type='expand')
        new_food_10 = pd.concat([food, applied_food_10], axis='columns')
        applied_food_10.rename(columns={'steps_typoed': 'steps_typoed_fivefold'}, inplace=True)

        food_t = pd.concat([applied_food_6, applied_food_7, applied_food_8, applied_food_9, applied_food_10], axis='columns')

        if args.store_file:
            ###saving to file
            filename = "food_modified_typos_" + args.sort_of_typo + ".jsonl"
            with open(filename, "w") as f:
                f.write(food_t.to_json(orient='records',lines=True, force_ascii=False))

    if (args.domain == "drone" or a) and args.typo:
        ###apply to dataframe and add results as new column: add n random typos in the conclusions of w steps 
        applied_drone_6 = drone.apply(lambda row: add_typo(row.proof, 1, 1, typo=args.sort_of_typo), axis='columns', result_type='expand')
        new_drone_6 = pd.concat([drone, applied_drone_6], axis='columns')
        applied_drone_6.rename(columns={'steps_typoed': 'steps_typoed_once'}, inplace=True)
        applied_drone_7 = drone.apply(lambda row: add_typo(row.proof, 2, 1, typo=args.sort_of_typo, cont=True), axis='columns', result_type='expand')
        new_drone_7 = pd.concat([drone, applied_drone_7], axis='columns')
        applied_drone_7.rename(columns={'steps_typoed': 'steps_typoed_twice'}, inplace=True)
        applied_drone_8 = drone.apply(lambda row: add_typo(row.proof, 3, 1, typo=args.sort_of_typo, cont=True), axis='columns', result_type='expand')
        new_drone_8 = pd.concat([drone, applied_drone_8], axis='columns')
        applied_drone_8.rename(columns={'steps_typoed': 'steps_typoed_thrice'}, inplace=True)
        applied_drone_9 = drone.apply(lambda row: add_typo(row.proof, 4, 1, typo=args.sort_of_typo, cont=True), axis='columns', result_type='expand')
        new_drone_9 = pd.concat([drone, applied_drone_9], axis='columns')
        applied_drone_9.rename(columns={'steps_typoed': 'steps_typoed_fourfold'}, inplace=True)
        applied_drone_10 = drone.apply(lambda row: add_typo(row.proof, 5, 1, typo=args.sort_of_typo, cont=True), axis='columns', result_type='expand')
        new_drone_10 = pd.concat([drone, applied_drone_10], axis='columns')
        applied_drone_10.rename(columns={'steps_typoed': 'steps_typoed_fivefold'}, inplace=True)

        drone_t = pd.concat([applied_drone_6, applied_drone_7, applied_drone_8, applied_drone_9, applied_drone_10], axis='columns')

        if args.store_file:
            ###saving to file
            filename = "drone_modified_typos_" + args.sort_of_typo + ".jsonl"
            with open(filename, "w") as f:
                f.write(drone_t.to_json(orient='records',lines=True, force_ascii=False))
