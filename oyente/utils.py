# return true if the two paths have different flows of money
# later on we may want to return more meaningful output: e.g. if the concurrency changes
# the amount of money or the recipient.
#如果两条路径的资金流不同，返回true
#稍后，我们可能想要返回更有意义的输出:例如，如果并发性改变
#金额或收款人。
import shlex
import subprocess
import json
import mmap
import os
import errno
import signal
import csv
import re
import difflib
import six
from z3 import *
from z3.z3util import get_vars

def ceil32(x):
    return x if x % 32 == 0 else x + 32 - (x % 32)#x向上取32的倍数

def isSymbolic(value):
    return not isinstance(value, six.integer_types)#不是整数，则是变量

def isReal(value):
    return isinstance(value, six.integer_types)#这里针对python2和python3中各自支持的int类型进行了区分：在python2中，存在 int 和 long 两种整数类型；在python3中，仅存在一种类型int。

def isAllReal(*args):#全是整数
    for element in args:
        if isSymbolic(element):
            return False
    return True

def to_symbolic(number):
    if isReal(number):
        return BitVecVal(number, 256)#整数转换为256位的位向量
    return number

def to_unsigned(number):
    if number < 0:
        return number + 2**256#复数转换为无符号整数
    return number

def to_signed(number):
    if number > 2**(256 - 1):#向上溢出为负数
        return (2**(256) - number) * (-1)
    else:
        return number

def check_sat(solver, pop_if_exception=True):#检查是否有解
    try:
        ret = solver.check()
        if ret == unknown:
            raise Z3Exception(solver.reason_unknown())#reason_unknown()Return a string describing why the last `check()` returned `unknown`.
    except Exception as e:
        if pop_if_exception:
            solver.pop()
        raise e
    return ret

def custom_deepcopy(input):#自定义深拷贝
    output = {}
    for key in input:
        if isinstance(input[key], list):
            output[key] = list(input[key])
        elif isinstance(input[key], dict):
            output[key] = custom_deepcopy(input[key])
        else:
            output[key] = input[key]
    return output


def is_storage_var(var):
    if not isinstance(var, str): var = var.decl().name()
    return var.startswith('Ia_store')


# copy only storage values/ variables from a given global state
#只从给定的全局状态复制存储值/变量
# TODO: add balance in the future
def copy_global_values(global_state):
    return global_state['Ia']

# check if a variable is in an expression#检查变量是否在表达式中
def is_in_expr(var, expr):
    list_vars = get_vars(expr)
    set_vars = set(i.decl().name() for i in list_vars)
    return var in set_vars


# check if an expression has any storage variables#检查表达式是否有存储变量
def has_storage_vars(expr, storage_vars):
    list_vars = get_vars(expr)
    for var in list_vars:
        if var in storage_vars:
            return True
    return False


def get_all_vars(exprs):#返回表达式中的变量
    ret_vars = []
    for expr in exprs:
        if is_expr(expr):
            ret_vars += get_vars(expr)
    return ret_vars


def get_storage_position(var):
    if not isinstance(var, str): var = var.decl().name()
    pos = var.split('-')[1]
    try: return int(pos)
    except: return pos

# Rename variables to distinguish variables in two different paths.
# e.g. Ia_store_0 in path i becomes Ia_store_0_old if Ia_store_0 is modified
# else we must keep Ia_store_0 if its not modified
#重命名变量，以区分两个不同路径中的变量。例如，如果Ia_store_0被修改，路径i中的Ia_store_0将变成Ia_store_0_old，否则，如果Ia_store_0没有被修改，我们必须保持Ia_store_0
def rename_vars(pcs, global_states):
    ret_pcs = []
    vars_mapping = {}

    for expr in pcs:
        if is_expr(expr):
            list_vars = get_vars(expr)
            for var in list_vars:
                if var in vars_mapping:
                    expr = substitute(expr, (var, vars_mapping[var]))
                    continue
                var_name = var.decl().name()
                # check if a var is global
                if is_storage_var(var):
                    pos = get_storage_position(var)
                    # if it is not modified then keep the previous name#如果没有修改，则保持原来的名称
                    if pos not in global_states:
                        continue
                # otherwise, change the name of the variable否则修改名称
                new_var_name = var_name + '_old'
                new_var = BitVec(new_var_name, 256)#使用新名称
                vars_mapping[var] = new_var
                expr = substitute(expr, (var, vars_mapping[var]))#替换
        ret_pcs.append(expr)#新变量列表

    ret_gs = {}
    # replace variable in storage expression#替换存储表达式中的变量
    for storage_addr in global_states:
        expr = global_states[storage_addr]
        # z3 4.1 makes me add this line
        if is_expr(expr):
            list_vars = get_vars(expr)
            for var in list_vars:
                if var in vars_mapping:
                    expr = substitute(expr, (var, vars_mapping[var]))
                    continue
                var_name = var.decl().name()
                # check if a var is global
                if var_name.startswith("Ia_store_"):
                    position = int(var_name.split('_')[len(var_name.split('_'))-1])
                    # if it is not modified
                    if position not in global_states:
                        continue
                # otherwise, change the name of the variable否则修改名称
                new_var_name = var_name + '_old'
                new_var = BitVec(new_var_name, 256)
                vars_mapping[var] = new_var
                expr = substitute(expr, (var, vars_mapping[var]))
        ret_gs[storage_addr] = expr

    return ret_pcs, ret_gs


# split a file into smaller files分解一个文件到更小的文件
def split_dicts(filename, nsub = 500):
    with open(filename) as json_file:
        c = json.load(json_file)
        current_file = {}
        file_index = 1
        for u, v in c.iteritems():
            current_file[u] = v
            if len(current_file) == nsub:#每500个字符分解为一个文件
                with open(filename.split(".")[0] + "_" + str(file_index) + '.json', 'w') as outfile:
                    json.dump(current_file, outfile)
                    file_index += 1
                    current_file.clear()
        if len(current_file):
            with open(filename.split(".")[0] + "_" + str(file_index) + '.json', 'w') as outfile:
                json.dump(current_file, outfile)
                current_file.clear()


def do_split_dicts():
    for i in range(11):
        split_dicts("contract" + str(i) + ".json")#分解大文件
        os.remove("contract" + str(i) + ".json")#删除原大文件


def run_re_file(re_str, fn):
    size = os.stat(fn).st_size
    with open(fn, 'r') as tf:
        data = mmap.mmap(tf.fileno(), size, access=mmap.ACCESS_READ)
        return re.findall(re_str, data)


def get_contract_info(contract_addr):#
    six.print_("Getting info for contracts... " + contract_addr)
    file_name1 = "tmp/" + contract_addr + "_txs.html"
    file_name2 = "tmp/" + contract_addr + ".html"
    # get number of txs获得交易的参数
    txs = "unknown"
    value = "unknown"
    re_txs_value = r"<span>A total of (.+?) transactions found for address</span>"
    re_str_value = r"<td>ETH Balance:\n<\/td>\n<td>\n(.+?)\n<\/td>"
    try:
        txs = run_re_file(re_txs_value, file_name1)
        value = run_re_file(re_str_value, file_name2)
    except Exception as e:
        try:
            os.system("wget -O %s http://etherscan.io/txs?a=%s" % (file_name1, contract_addr))#获取线上合约的交易参数
            re_txs_value = r"<span>A total of (.+?) transactions found for address</span>"
            txs = run_re_file(re_txs_value, file_name1)

            # get balance
            re_str_value = r"<td>ETH Balance:\n<\/td>\n<td>\n(.+?)\n<\/td>"
            os.system("wget -O %s https://etherscan.io/address/%s" % (file_name2, contract_addr))
            value = run_re_file(re_str_value, file_name2)
        except Exception as e:
            pass
    return txs, value


def get_contract_stats(list_of_contracts):
    with open("concurr.csv", "w") as stats_file:#写入合约的参数
        fp = csv.writer(stats_file, delimiter=',')
        fp.writerow(["Contract address", "No. of paths", "No. of concurrency pairs", "Balance", "No. of TXs", "Note"])#写入csv文件的一行作为表头
        with open(list_of_contracts, "r") as f:
            for contract in f.readlines():
                contract_addr = contract.split()[0]
                value, txs = get_contract_info(contract_addr)
                fp.writerow([contract_addr, contract.split()[1], contract.split()[2],
                             value, txs, contract.split()[3:]])#写入合约地址，合约路径数，合约的冲突对，合约的余额，合约的交易数，合约的note


def get_time_dependant_contracts(list_of_contracts):
    with open("time.csv", "w") as stats_file:
        fp = csv.writer(stats_file, delimiter=',')
        fp.writerow(["Contract address", "Balance", "No. of TXs", "Note"])
        with open(list_of_contracts, "r") as f:
            for contract in f.readlines():
                if len(contract.strip()) == 0:
                    continue
                contract_addr = contract.split(".")[0].split("_")[1]
                txs, value = get_contract_info(contract_addr)
                fp.writerow([contract_addr, value, txs])


def get_distinct_contracts(list_of_contracts = "concurr.csv"):
    flag = []
    with open(list_of_contracts, "rb") as csvfile:
        contracts = csvfile.readlines()[1:]
        n = len(contracts)
        for i in range(n):
            flag.append(i) # mark which contract is similar to contract_i
        for i in range(n):
            if flag[i] != i:
                continue
            contract_i = contracts[i].split(",")[0]
            npath_i = int(contracts[i].split(",")[1])
            npair_i = int(contracts[i].split(",")[2])
            file_i = "stats/tmp_" + contract_i + ".evm"
            six.print_(" reading file " + file_i)
            for j in range(i+1, n):
                if flag[j] != j:
                    continue
                contract_j = contracts[j].split(",")[0]
                npath_j = int(contracts[j].split(",")[1])
                npair_j = int(contracts[j].split(",")[2])
                if (npath_i == npath_j) and (npair_i == npair_j):
                    file_j = "stats/tmp_" + contract_j + ".evm"

                    with open(file_i, 'r') as f1, open(file_j, 'r') as f2:
                        code_i = f1.readlines()
                        code_j = f2.readlines()
                        if abs(len(code_i) - len(code_j)) >= 5:
                            continue
                        diff = difflib.ndiff(code_i, code_j)
                        ndiff = 0
                        for line in diff:
                            if line.startswith("+") or line.startswith("-"):
                                ndiff += 1
                        if ndiff < 10:
                            flag[j] = i
    six.print_(flag)

def run_command(cmd):
    FNULL = open(os.devnull, 'w')
    solc_p = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=FNULL)
    #shlex.split(s, comments=False, posix=True)
    #用类似 shell 的语法拆分字符串 s。如果 comments 为 False (默认值)，则不会解析给定字符串中的注释 (commenters 属性的 shlex 实例设为空字符串)。 
    #本函数默认工作于 POSIX 模式下，但若 posix 参数为 False，则采用非 POSIX 模式。
    return solc_p.communicate()[0].decode('utf-8', 'strict')

def run_command_with_err(cmd):
    FNULL = open(os.devnull, 'w')
    solc_p = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = solc_p.communicate()
    out = out.decode('utf-8', 'strict')
    err = err.decode('utf-8', 'strict')
    return out, err

