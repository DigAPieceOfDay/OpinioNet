from pytorch_pretrained_bert import BertTokenizer
from dataset import ReviewDataset, get_data_loaders
from model import OpinioNet

import torch
from torch.utils.data import DataLoader

from tqdm import tqdm
import os.path as osp
import pandas as pd
from dataset import ID2C, ID2P, ID2LAPTOP
from collections import Counter


def eval_epoch(model, dataloader, th):
	model.eval()
	step = 0
	result = []
	pbar = tqdm(dataloader)
	for raw, x, _ in pbar:
		if step == len(dataloader):
			pbar.close()
			break
		rv_raw, _ = raw
		x = [item.cuda() for item in x]
		with torch.no_grad():
			probs, logits = model.forward(x, 'laptop')
			pred_result = model.gen_candidates(probs)
			pred_result = model.nms_filter(pred_result, th)

		result += pred_result

		step += 1
	return result


def accum_result(old, new):
	if old is None:
		return new
	for i in range(len(old)):
		merged = Counter(dict(old[i])) + Counter(dict(new[i]))
		old[i] = list(merged.items())
	return old


def average_result(result, num):
	for i in range(len(result)):
		for j in range(len(result[i])):
			result[i][j] = (result[i][j][0], result[i][j][1] / num)
	return result


def gen_submit(ret, raw):
	result = pd.DataFrame(columns=['id', 'A', 'O', 'C', 'P'])
	cur_idx = 1
	for i, opinions in enumerate(ret):

		if len(opinions) == 0:
			result = result.append({'id': cur_idx, 'A': '_', 'O': '_', 'C': '_', 'P': '_'}, ignore_index=True)

		for j, (opn, score) in enumerate(opinions):
			a_s, a_e, o_s, o_e = opn[0:4]
			c, p = opn[4:6]
			if a_s == 0:
				A = '_'
			else:
				A = raw[i][a_s - 1: a_e]
			if o_s == 0:
				O = '_'
			else:
				O = raw[i][o_s - 1: o_e]
			C = ID2LAPTOP[c]
			P = ID2P[p]
			result = result.append({'id': cur_idx, 'A': A, 'O': O, 'C': C, 'P': P}, ignore_index=True)
		cur_idx += 1
	return result

import json
from config import PRETRAINED_MODELS
if __name__ == '__main__':
	SAVING_DIR = '../models/'
	THRESH_DIR = '../models/thresh_dict.json'
	with open(THRESH_DIR, 'r', encoding='utf-8') as f:
		thresh_dict = json.load(f)

	WEIGHT_NAMES, MODEL_NAMES, THRESHS = [], [], []
	for k, v in thresh_dict.items():
		WEIGHT_NAMES.append(k)
		MODEL_NAMES.append(v['name'])
		THRESHS.append(v['thresh'])

	MODELS = list(zip(WEIGHT_NAMES, MODEL_NAMES, THRESHS))
	tokenizer = BertTokenizer.from_pretrained(PRETRAINED_MODELS['roberta']['path'], do_lower_case=True)
	test_dataset = ReviewDataset('../data/TEST/Test_reviews.csv', None, tokenizer, 'laptop')
	test_loader = DataLoader(test_dataset, 12, collate_fn=test_dataset.batchify, shuffle=False, num_workers=5)
	ret = None
	num_model = 0
	for weight_name, model_name, thresh in MODELS:
		if not osp.isfile('../models/' + weight_name):
			continue
		num_model += 1
		tokenizer = BertTokenizer.from_pretrained(PRETRAINED_MODELS[model_name]['path'], do_lower_case=True)
		test_dataset = ReviewDataset('../data/TEST/Test_reviews.csv', None, tokenizer, 'laptop')
		test_loader = DataLoader(test_dataset, 12, collate_fn=test_dataset.batchify, shuffle=False, num_workers=5)
		model = OpinioNet.from_pretrained(PRETRAINED_MODELS[model_name]['path'])
		model.load_state_dict(torch.load('../models/' + weight_name))
		model.cuda()
		ret = accum_result(ret, eval_epoch(model, test_loader, thresh))
		del model
	ret = average_result(ret, num_model)
	# import numpy as np
	# import copy
	#
	# min_dis = float('inf')
	# threshs = list(np.arange(0.1, 0.9, 0.05))
	# result = None
	# target_num = len(test_dataset) * 2456 / 871
	# raw = [s[0][0] for s in test_dataset.samples]
	# for th in threshs:
	# 	ret_cp = copy.deepcopy(ret)
	# 	ret_cp = OpinioNet.nms_filter(ret_cp, th)
	# 	cur_result = gen_submit(ret_cp, raw)
	#
	# 	if abs(cur_result.shape[0] - target_num) < min_dis:
	# 		min_dis = abs(cur_result.shape[0] - target_num)
	# 		result = cur_result

	ret = OpinioNet.nms_filter(ret, 0.3)
	raw = [s[0][0] for s in test_dataset.samples]
	result = gen_submit(ret, raw)

	# import time
	# result.to_csv('../submit/ensemble-' + str(round(time.time())) + '.csv', header=False, index=False)
	result.to_csv('../submit/Result.csv', header=False, index=False)
	print(len(result['id'].unique()), result.shape[0])