import re
import six
import ast
import json

import global_params

from utils import run_command
from ast_helper import AstHelper

class Source:
    def __init__(self, filename):
        self.filename = filename#source对象映射到文件名
        self.content = self._load_content()#文件内容，utf8编码
        self.line_break_positions = self._load_line_break_positions()

    def _load_content(self):
        with open(self.filename, 'rb') as f:#读文件，二进制到utf8
            content = f.read().decode('UTF-8')
        return content

    def _load_line_break_positions(self):#换行符所在文件中的字符序号就是line_break_position，构成的列表是line_break_positions
        return [i for i, letter in enumerate(self.content) if letter == '\n']#分行，得到行号i；如果遍历到换行符，则返回换行符所在的字符序号，字符序号构成一个列表

class SourceMap:
    parent_filename = ""
    position_groups = {}
    sources = {}
    ast_helper = None
    func_to_sig_by_contract = {}
    remap = ""
    allow_paths = ""

    def __init__(self, cname, parent_filename, input_type, root_path="", remap="", allow_paths=""):
        self.root_path = root_path
        self.cname = cname#contract name
        self.input_type = input_type#solidity或者json
        if not SourceMap.parent_filename:
            SourceMap.remap = remap
            SourceMap.allow_paths = allow_paths
            SourceMap.parent_filename = parent_filename
            if input_type == "solidity":
                SourceMap.position_groups = SourceMap._load_position_groups()
            elif input_type == "standard json":
                SourceMap.position_groups = SourceMap._load_position_groups_standard_json()
            else:
                raise Exception("There is no such type of input")
            SourceMap.ast_helper = AstHelper(SourceMap.parent_filename, input_type, SourceMap.remap, SourceMap.allow_paths)
            SourceMap.func_to_sig_by_contract = SourceMap._get_sig_to_func_by_contract()
            #ast_helper: 存储着合约的各种索引和输出合约索引和状态的辅助类函数。
            #source：是一个在source_map中定义的结构体，保存了合约的字段。
            #sources：应该是在多个源的时候使用。
            #position_groups：包含着编译好的字节指令asm和辅助签名数据auxdata
            #其中begin映射着合约函数某函数开始的字符串位置，end映射着合约函数结束的字符串位置。
            #案例：{'begin': 27, 'end': 141, 'name': 'PUSH', 'value': '60'}
            #pragma solidity >=0.4.19;
            #/*现在处于第27个字符*/
            #contract test {
            #    function helloworld() pure public returns (string)
            #    {
            #        return "hello world";
            #    }
            #}
            #/*现在处于第141个字符*/
        self.source = self._get_source()
        self.positions = self._get_positions()
        self.instr_positions = {}
        self.var_names = self._get_var_names()
        self.func_call_names = self._get_func_call_names()
        self.callee_src_pairs = self._get_callee_src_pairs()
        self.func_name_to_params = self._get_func_name_to_params()
        self.sig_to_func = self._get_sig_to_func()

    def get_source_code(self, pc):#
        try:
            pos = self.instr_positions[pc]#
        except:
            return ""
        begin = pos['begin']
        end = pos['end']
        return self.source.content[begin:end]

    def get_source_code_from_src(self, src):
        src = src.split(":")#
        start = int(src[0])
        end = start + int(src[1])
        return self.source.content[start:end]#根据起止位置截取源码

    def get_buggy_line(self, pc):#pc:program counter
        try:
            pos = self.instr_positions[pc]
        except:
            return ""
        location = self.get_location(pc)
        begin = self.source.line_break_positions[location['begin']['line'] - 1] + 1
        end = pos['end']
        return self.source.content[begin:end]

    def get_buggy_line_from_src(self, src):
        pos = self._convert_src_to_pos(src)
        location = self.get_location_from_src(src)
        begin = self.source.line_break_positions[location['begin']['line'] - 1] + 1
        end = pos['end']
        return self.source.content[begin:end]

    def get_location(self, pc):
        pos = self.instr_positions[pc]
        return self._convert_offset_to_line_column(pos)

    def get_location_from_src(self, src):
        pos = self._convert_src_to_pos(src)
        return self._convert_offset_to_line_column(pos)

    def get_parameter_or_state_var(self, var_name):
        try:
            names = [
                node.id for node in ast.walk(ast.parse(var_name))
                if isinstance(node, ast.Name)
            ]
            if names[0] in self.var_names:
                return var_name
        except:
            return None
        return None

    def _convert_src_to_pos(self, src):
        pos = {}
        src = src.split(":")
        pos['begin'] = int(src[0])
        length = int(src[1])
        pos['end'] = pos['begin'] + length - 1
        return pos

    def _get_sig_to_func(self):
        func_to_sig = SourceMap.func_to_sig_by_contract[self.cname]['hashes']
        return dict((sig, func) for func, sig in six.iteritems(func_to_sig))

    def _get_func_name_to_params(self):
        func_name_to_params = SourceMap.ast_helper.get_func_name_to_params(self.cname)
        for func_name in func_name_to_params:
            calldataload_position = 0
            for param in func_name_to_params[func_name]:
                if param['type'] == 'ArrayTypeName':
                    param['position'] = calldataload_position
                    calldataload_position += param['value']
                else:
                    param['position'] = calldataload_position
                    calldataload_position += 1
        return func_name_to_params

    def _get_source(self):
        fname = self.get_filename()
        if fname not in SourceMap.sources:#添加原来没有sourcemap的文件，构造一个字典，key是fname，value是Source对象，Source对象传入fname
            SourceMap.sources[fname] = Source(fname)
        return SourceMap.sources[fname]#返回文件名对应的Source对象

    def _get_callee_src_pairs(self):
        return SourceMap.ast_helper.get_callee_src_pairs(self.cname)

    def _get_var_names(self):
        return SourceMap.ast_helper.extract_state_variable_names(self.cname)

    def _get_func_call_names(self):
        func_call_srcs = SourceMap.ast_helper.extract_func_call_srcs(self.cname)
        func_call_names = []
        for src in func_call_srcs:
            src = src.split(":")
            start = int(src[0])
            end = start + int(src[1])
            func_call_names.append(self.source.content[start:end])
        return func_call_names

    @classmethod
    def _get_sig_to_func_by_contract(cls):#当类调用classmethod方法时，默认把此类传进去
        if cls.allow_paths:
            cmd = 'solc --combined-json hashes %s %s --allow-paths %s' % (cls.remap, cls.parent_filename, cls.allow_paths)
        else:
            cmd = 'solc --combined-json hashes %s %s' % (cls.remap, cls.parent_filename)
        out = run_command(cmd)
        out = json.loads(out)
        return out['contracts']

    @classmethod
    def _load_position_groups_standard_json(cls):
        with open('standard_json_output', 'r') as f:
            output = f.read()
        output = json.loads(output)
        return output["contracts"]

    @classmethod
    def _load_position_groups(cls):
        if cls.allow_paths:
            cmd = "solc --combined-json asm %s %s --allow-paths %s" % (cls.remap, cls.parent_filename, cls.allow_paths)
        else:
            cmd = "solc --combined-json asm %s %s" % (cls.remap, cls.parent_filename)
        out = run_command(cmd)
        out = json.loads(out)
        return out['contracts']

    def _get_positions(self):
        if self.input_type == "solidity":
            asm = SourceMap.position_groups[self.cname]['asm']['.data']['0']#asm中的动态段的开始位置
        else:
            filename, contract_name = self.cname.split(":")#cname的样式是文件名:合约名
            asm = SourceMap.position_groups[filename][contract_name]['evm']['legacyAssembly']['.data']['0']#evm.legacyAssembly - Old-style assembly format in JSON
        positions = asm['.code']#是静态段.code
        while(True):
            try:
                positions.append(None)
                positions += asm['.data']['0']['.code']#动态段的.data
                asm = asm['.data']['0']
            except:
                break
        return positions

    def _convert_offset_to_line_column(self, pos):#偏移量到行号列号
        ret = {}
        ret['begin'] = None
        ret['end'] = None
        if pos['begin'] >= 0 and (pos['end'] - pos['begin'] + 1) >= 0:
            ret['begin'] = self._convert_from_char_pos(pos['begin'])
            ret['end'] = self._convert_from_char_pos(pos['end'])
        return ret

    def _convert_from_char_pos(self, pos):
        line = self._find_lower_bound(pos, self.source.line_break_positions)
        if self.source.line_break_positions[line] != pos:
            line += 1
        begin_col = 0 if line == 0 else self.source.line_break_positions[line - 1] + 1
        col = pos - begin_col
        return {'line': line, 'column': col}

    def _find_lower_bound(self, target, array):#
        start = 0
        length = len(array)
        while length > 0:
            half = length >> 1
            middle = start + half#中间位置
            if array[middle] <= target:
                length = length - 1 - half
                start = middle + 1
            else:
                length = half
        return start - 1

    def get_filename(self):#文件名
        return self.cname.split(":")[0]
