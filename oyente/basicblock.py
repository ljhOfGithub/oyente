import six

class BasicBlock:
    def __init__(self, start_address, end_address):
        self.start = start_address
        self.end = end_address
        self.instructions = []  # each instruction is a string
        self.jump_target = 0

    def get_start_address(self):
        return self.start

    def get_end_address(self):
        return self.end

    def add_instruction(self, instruction):
        self.instructions.append(instruction)

    def get_instructions(self):#获得基本块中的指令列表
        return self.instructions

    def set_block_type(self, type):#当前分支的类型，如有条件跳转和无条件跳转
        self.type = type

    def get_block_type(self):
        return self.type

    def set_falls_to(self, address):#设置无跳转时的下一个块
        self.falls_to = address

    def get_falls_to(self):
        return self.falls_to

    def set_jump_target(self, address):
        if isinstance(address, six.integer_types):
            self.jump_target = address
        else:
            self.jump_target = -1

    def get_jump_target(self):
        return self.jump_target

    def set_branch_expression(self, branch):#设置分支表达式
        self.branch_expression = branch

    def get_branch_expression(self):
        return self.branch_expression

    def display(self):
        six.print_("================")
        six.print_("start address: %d" % self.start)
        six.print_("end address: %d" % self.end)
        six.print_("end statement type: " + self.type)
        for instr in self.instructions:
            six.print_(instr)
