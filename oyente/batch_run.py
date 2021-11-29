import json
import glob#glob — Unix style pathname pattern expansion
from tqdm import tqdm#进度条类
import os
import sys
import urllib2

contract_dir = 'contract_data'

cfiles = glob.glob(contract_dir+'/contract1.json')

cjson = {}

print "Loading contracts..."

for cfile in tqdm(cfiles):#
	cjson.update(json.loads(open(cfile).read()))#json.loads(open(cfile).read())产生一个字典,键是合约名，值是合约内容

results = {}
missed = []

print "Running analysis..."

contracts = cjson.keys()

if os.path.isfile('results.json'):
	old_res = json.loads(open('results.json').read())
	old_res = old_res.keys()#旧repository里的合约名
	contracts = [c for c in contracts if c not in old_res]#挑选不在旧repository里面的合约名，即不重复分析已经分析过的合约

cores=0
job=0

if len(sys.argv)>=3:
	cores = int(sys.argv[1])
	job = int(sys.argv[2])#分批分析
	contracts = contracts[(len(contracts)/cores)*job:(len(contracts)/cores)*(job+1)]#要分析的合约列表
	print "Job %d: Running on %d contracts..." % (job, len(contracts))

for c in tqdm(contracts):#c是一个合约名
	with open('tmp.evm','w') as of:#不知道是什么文件
		of.write(cjson[c][1][2:])#[2:]是合约的0x后的
	os.system('python oyente.py -ll 30 -s tmp.evm -j -b')
	try:
		results[c] = json.loads(open('tmp.evm.json').read())
	except:
		missed.append(c)#出错记录遗漏的合约
	with open('results.json', 'w') as of:
		of.write(json.dumps(results,indent=1))
	with open('missed.json', 'w') as of:
		of.write(json.dumps(missed,indent=1))
	# urllib2.urlopen('https://dweet.io/dweet/for/oyente-%d-%d?completed=%d&missed=%d&remaining=%d' % (job,cores,len(results),len(missed),len(contracts)-len(results)-len(missed)))

print "Completed."
