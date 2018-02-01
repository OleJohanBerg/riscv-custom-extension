#!/usr/bin/env python

import argparse
import clang.cindex
import logging
import os
import subprocess
import sys

from mako.template import Template

logging.basicConfig(stream=sys.stdout)
logger = logging.getLogger(__name__)


class Model:
    '''
    C++ Reference of the custom instruction.
    '''

    def __init__(self, impl):

        # clang.cindex.Config.set_library_file('/usr/lib/llvm-4.0/lib/libclang-4.0.so')
        index = clang.cindex.Index.create()
        tu = index.parse(
            impl, ['-x', 'c++', '-std=c++11'])

        self._name = ""
        self._dfn = ""
        self._form = "regreg"

        self.method_name(tu.cursor)
        self.method_definitions(tu.cursor)

    def method_name(self, node):
        for child in node.get_children():
            self.method_name(child)

        if node.kind == clang.cindex.CursorKind.FUNCTION_DECL:
            # print(node.spelling)
            self._name = node.spelling

    def method_definitions(self, node):
        for child in node.get_children():
            self.method_definitions(child)

        if node.kind == clang.cindex.CursorKind.COMPOUND_STMT:
            self.extract_definition(node)

    def extract_definition(self, node):
        filename = node.location.file.name
        with open(filename, 'r') as fh:
            contents = fh.read()
        # print(contents[node.extent.start.offset: node.extent.end.offset])
        self._dfn = contents[node.extent.start.offset: node.extent.end.offset]

    @property
    def form(self):
        return self._form

    @property
    def definition(self):
        return self._dfn

    @property
    def name(self):
        return self._name


class Instruction:
    '''
    Class, that represents one single custom instruction.
    Contains the name, the mask and the match.
    '''

    def __init__(self, form, funct3, funct7, mask, match, name, opc):
        self._form = form  # format
        self._funct3 = funct3  # funct3 encoding
        self._funct7 = funct7  # funct7 encoding, used by reg reg ops
        self._mask = mask  # the mask name
        self._match = match  # the match name
        self._name = name  # the name that shall occure in the assembler
        self._opc = opc  # opcode - inst[6:2]

    @property
    def form(self):
        return self._form

    @property
    def funct3(self):
        return self._funct3

    @property
    def funct7(self):
        return self._funct7

    @property
    def mask(self):
        return self._mask

    @property
    def match(self):
        return self._match

    @property
    def name(self):
        return self._name

    @property
    def opc(self):
        return self._opc


class Extensions:
    '''
    Has all necessary information about the custom instructions
    that is needed to extend the RISC-V assembler.
    '''

    def __init__(self, models):
        self._models = models
        self._insts = []

        for model in models:
            self.model_to_inst(model)

    def model_to_inst(self, model):
        opcodes_cust = Template(filename='opcodes-cust.mako')

        opc_cust = 'opcodes-cust'
        with open(opc_cust, 'w') as fh:
            fh.write(opcodes_cust.render(models=self._models))

        with open(opc_cust, 'r') as fh:
            ops = fh.read()

        try:
            os.remove(opc_cust)
        except OSError:
            pass

        p = subprocess.Popen(['riscv-opcodes/parse-opcodes',
                              '-c'],
                             stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE)
        defines, _ = p.communicate(input=ops)

        d = '\n'
        lines = [e + d for e in defines.split(d)]

        self._masks = [
            entry for entry in lines if entry.startswith('#define MASK')]
        self._matches = [
            entry for entry in lines if entry.startswith('#define MATCH')]
        self._mask_names = [
            entry for entry in self._masks for entry in entry.split()
            if entry.startswith('MASK')]
        self._match_names = [
            entry for entry in self._matches for entry in entry.split()
            if entry.startswith('MATCH')]

        assert len(self._masks) == len(
            self._matches), 'Length of mask and match arrays differ'

    @property
    def models(self):
        return self._models

    @property
    def funcnames(self):
        return self._names

    @property
    def matches(self):
        return self._matches

    @property
    def masks(self):
        return self._masks

    @property
    def matchnames(self):
        return self._match_names

    @property
    def masknames(self):
        return self._mask_names


def parse_model(args):
    '''
    Parse the c++ reference implementation
    of the custom instruction.
    '''

    model = Model(args.model)
    return model


def extend_assembler(models):
    '''
    Create a temporary file from which the opcode
    of the custom instruction is going to be generated.
    '''
    extensions = Extensions(models)

    masks = extensions.masks
    matches = extensions.matches

    # files that needs to be edited
    opch = 'riscv-gnu-toolchain/riscv-binutils-gdb/include/opcode/riscv-opc.h'
    opcc = 'riscv-gnu-toolchain/riscv-binutils-gdb/opcodes/riscv-opc.c'

    # the mask and match defines has to be added in the header file
    with open(opch, 'r') as fh:
        content = fh.readlines()

    for i in range(0, len(masks)):
        # check if entry exists
        # skip this instruction if so
        # prevents double define for old custom extensions, if new one was
        # added
        if masks[i] in content:
            continue

        # first line number, where the new opcode can be inserted is 3
        content.insert(i + 3, masks[i])
        content.insert(i + 3, matches[i])

    with open(opch, 'w') as fh:
        content = ''.join(content)
        fh.write(content)

    # in the c file the asm instruction is defined
    # build string that has to be inserted

    inst_def_templ = Template(filename='inst-definition.mako')
    inst_def = 'inst_def'

    with open(inst_def, 'w') as fh:
        fh.write(inst_def_templ.render(extensions=extensions,
                                       opcc=opcc))


def main():
    '''
    Main function.
    '''

    # argparsing
    parser = argparse.ArgumentParser(
        prog='extparser',
        description='Parse reference implementations of custom extension ' +
        'models.')

    parser.add_argument('-v',
                        '--verbosity',
                        default=0,
                        action='count',
                        help='Increase output verbosity.')
    parser.add_argument('-b',
                        '--build',
                        action='store_true',
                        help='If set, Toolchain and Gem5 will be ' +
                        'rebuild.')
    parser.add_argument('-m',
                        '--model',
                        type=str,
                        default=os.path.join(
                            os.path.dirname(__file__),
                            'extensions',
                            'test.cc'),
                        help='Reference implementation')

    args = parser.parse_args()

    logger.setLevel(50 - 10 * args.verbosity)

    models = []
    models.append(parse_model(args))
    extend_assembler(models)


if __name__ == '__main__':
    main()