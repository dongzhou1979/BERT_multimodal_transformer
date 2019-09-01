#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Feb  7 13:06:48 2019

@author: echowdh2
"""

#from staged_multimodal_transformer_driver import ex
import os
import argparse, sys
import global_configs
from global_configs import *
from sacred import Experiment
import time
import numpy as np
import torch
import six
import random

skeleton_ex = Experiment('launcher')
#works on text only
from xlnet_mosi_driver import xlnet_ex
from xlnet_multi_mosi_driver import xlnet_multi_ex
from xlnet_multi_mosei_driver import xlnet_multi_mosei_ex

import optuna
from sqlalchemy import create_engine

parser=argparse.ArgumentParser()
parser.add_argument('--dataset', help='the dataset you want to work on')
parser.add_argument('--multi', action='store_true', default=False)
parser.add_argument('--load_study', action='store_true', default=False)
parser.add_argument('--device', default='cuda:0')
args = parser.parse_args()
dataset_path = os.path.join(all_datasets_location,args.dataset)
print(dataset_path)

device_num = int(args.device[-1])
torch.cuda.set_device(device_num)

if args.multi:
    DB = 'sqlite:///hparam_search/xlnet_multi_' + args.dataset + '.db'
    if not os.path.exists('./hparam_search/xlnet_multi_' + args.dataset + '.db'):
        engine = create_engine(DB)
else:
    DB = 'sqlite:///hparam_search/xlnet_' + args.dataset + '.db'
    if not os.path.exists('./hparam_search/xlnet_' + args.dataset + '.db'):
        engine = create_engine(DB)

dataset_specific_config = {
        #For  mosi, input_modailities_size do not matter
        "mosi":{'input_modalities_sizes':[300,5,20],'output_mode':'regression','label_list':[None],'dev_batch_size':229,'test_batch_size':685,'d_acoustic_in':74,'d_visual_in':47},
        "ETS":{'input_modalities_sizes':[1,81,35],'output_mode':'regression','label_list':[None],'dev_batch_size':229,'test_batch_size':685,'d_acoustic_in':81,'d_visual_in':35,'max_num_sentences':20,'max_seq_length':30, 'Y_size':6,'target_label_index':0},
        "iemocap":{'text_indices':(0,300),'audio_indices':(300,374),'video_indices':(374,409),'max_seq_len':21},
        "mmmo":{'text_indices':(0,300),'audio_indices':(300,374),'video_indices':(374,409),'max_seq_len':21},
        "moud":{'text_indices':(0,300),'audio_indices':(300,374),'video_indices':(374,409),'max_seq_len':21},
        "pom":{'text_indices':(0,300),'audio_indices':(300,343),'video_indices':(343,386),'max_seq_len':21},
        "youtube":{'text_indices':(0,300),'audio_indices':(300,374),'video_indices':(374,409),'max_seq_len':21},
        "mosei":{'input_modalities_sizes':[300,5,20],'output_mode':'regression','label_list':[None],'dev_batch_size':229,'test_batch_size':685,'d_acoustic_in':74,'d_visual_in':35},
        "MRPC":{}
        }

#sacred will generate a different random _seed for every experiment
#and we will use that seed to control the randomness emanating from our libraries
if(running_as_job_array == True):
 node_index=int(os.environ['SLURM_ARRAY_TASK_ID'])
else:
    node_index=50

#So, we are assuming that there will a folder called /processed_multimodal_data in the parent folder
#of this code. I wanted to keep it inside the .git folder. But git push limits file size to be <=100MB
#and some data files exceeds that size.

@skeleton_ex.config
def sk_config():
    dataset_location = None
    beta_shift = 0
    fc1_out = 0
    fc1_dropout=0
    h_audio_lstm = 0
    h_video_lstm = 0
    hidden_dropout_prob = 0
    learning_rate = 5e-5
    gradient_accumulation_steps = 1
    AV_index = 1
    train_batch_size = 32
    seed = 101

@skeleton_ex.command
def initiate_main_experiment(_config):
    #config_to_init_main=_config["skeleton_init_config"]
    dataset_location = _config["dataset_location"]

    dataset_name = dataset_location[dataset_location.rfind("/")+1:]

    main_init_configs = {**dataset_specific_config[dataset_name], "node_index":node_index, "prototype":conf_prototype, "dataset_location":dataset_location, "dataset_name":dataset_name}

    GLUE_DIR="/scratch/mhasan8/processed_multimodal_data/"#do not bother, legacy code

    #_config["seed"] = 167671700

    TASK_NAME=dataset_name
    main_init_configs["task_name"] = TASK_NAME
    main_init_configs["do_train"]  = True
    main_init_configs["do_eval"]  = True
    main_init_configs["data_dir"]  = GLUE_DIR + "/" +TASK_NAME
    main_init_configs["cache_dir"] = CACHE_DIR
    main_init_configs["xlnet_model"] = "xlnet-base-cased"
    main_init_configs["device"] = args.device

    #Relevant for us:Sangwu
    main_init_configs["max_seq_length"]  = 35 if args.dataset == 'mosi' else 50 #TODO:May be shortened
    main_init_configs["train_batch_size"] = _config["train_batch_size"]

    if args.multi:
        main_init_configs["acoustic_in_dim"] = 74
        main_init_configs["visual_in_dim"] = 47 if args.dataset == 'mosi' else 35
        main_init_configs["h_merge_sent"] = 768

    #main_init_configs["hidden_dropout_prob"]=0.45
    #main_init_configs["beta_shift"]=0

    main_init_configs["num_train_epochs"] = 30 if args.dataset == 'mosi' else 12
    #commenting out temporarily
    main_init_configs["output_dir"] =  "/tmp/"+TASK_NAME

    print("Main_Seed: ", _config["seed"])
    #fix the seed beforehand
    main_init_configs["seed"] = _config["seed"]

    main_init_configs["AV_index"] = _config["AV_index"]
    main_init_configs["learning_rate"] = _config["learning_rate"]
    main_init_configs["gradient_accumulation_steps"] = _config["gradient_accumulation_steps"]

    if args.multi:
        main_init_configs["hidden_dropout_prob"] = _config["hidden_dropout_prob"]
        main_init_configs["beta_shift"] = _config["beta_shift"]
        main_init_configs["h_audio_lstm"] = _config["h_audio_lstm"]
        main_init_configs["h_video_lstm"] = _config["h_video_lstm"]
        main_init_configs["fc1_out"] = _config["fc1_out"]
        main_init_configs["fc1_dropout"] = _config["fc1_dropout"]

    #print("inherited this configs:",main_init_configs,main_init_configs.keys())
    #result = bert_ex.run(command_name="main",config_updates=main_init_configs)
    #return
    if dataset_name=="mosi":
        if args.multi:
            result = xlnet_multi_ex.run(command_name="main",config_updates=main_init_configs)
        else:
            result = xlnet_ex.run(command_name="main",config_updates=main_init_configs)
    elif dataset_name=="mosei":
        result = xlnet_multi_mosei_ex.run(command_name="main",config_updates=main_init_configs)
    #must use seed for the main exp
    return result

def return_unk():
    return 0

def objective(trial):
    optuna_configs = {}
    optuna_configs["learning_rate"] = trial.suggest_categorical("learning_rate", [1e-5,1.5e-5,2e-5,2.5e-5,3e-5,3.5e-5,4e-5,4.5e-5,5e-5,5.5e-5,6e-5])
    optuna_configs["gradient_accumulation_steps"] = trial.suggest_categorical("gradient_accumulation_steps", [1,2,3])
    optuna_configs["AV_index"] = -2


    if args.multi:
        optuna_configs["hidden_dropout_prob"] = trial.suggest_categorical("hidden_dropout_prob", [0.1,0.2,0.25,0.3,0.35,0.4,0.45,0.5,0.55,0.6])
        optuna_configs["beta_shift"] = trial.suggest_categorical("beta_shift", [0.25,0.3,0.35,0.4,0.45,0.5,0.6,0.7,0.8,0.9,1,1.5,1.8,2,2.2,2.5,2.8,3,3.2,3.4,3.6,3.8,4,4.5,4.8,5,5.5,5.8,6,6.2,6.4,7,8,10,12,14,16,20,22,24,28,30,32,40,44,50,60,70,80,100])
        optuna_configs["h_audio_lstm"] =  trial.suggest_categorical("h_audio_lstm", [16])
        optuna_configs["h_video_lstm"] =  trial.suggest_categorical("h_video_lstm", [16])
        optuna_configs["fc1_out"] =  trial.suggest_categorical("fc1_out", [32])
        optuna_configs["fc1_dropout"] =  trial.suggest_categorical("fc1_dropout", [0.1])
        optuna_configs["AV_index"] = 1

    global_configs.EXP_TRIAL = trial
    optuna_configs["seed"] = random.randrange(2**32 -1)
    optuna_configs['dataset_location'] = dataset_path
    run = skeleton_ex.run(command_name='initiate_main_experiment',config_updates=optuna_configs)
    #r = ex.run(named_configs=['search_space'],config_updates={"node_index":node_index,"prototype":True})
    return run.result.info['best_test_acc']


#run it like ./bert_running_different_configs.py --dataset=mosi
#run: ./bert_running_different_configs.py --dataset=ETS
if __name__ == '__main__':
    global_configs.init_trial()
    if(os.path.isdir(dataset_path)):
        pruner = optuna.pruners.MedianPruner(n_startup_trials=15,n_warmup_steps=3)
        if args.load_study:
            study = optuna.load_study(study_name='m-XLNet hparam search', pruner=pruner, storage=DB)
        else:
            study = optuna.create_study(study_name='m-XLNet hparam search', pruner=pruner, direction='maximize', storage=DB, load_if_exists=True)
        study.optimize(objective, n_trials=18, n_jobs=1)
        print(study.best_trial)
    else:
        raise NotADirectoryError("Please input the dataset name correctly")

    # subfolders = [f.path for f in os.scandir(all_datasets_location) if f.is_dir() ]

    # for s_folder in subfolders:


    #     dataset_name = s_folder[s_folder.rfind("/")+1:]
    #     if dataset_name == args.dataset:
    #         run_a_config(s_folder)
    #         break
