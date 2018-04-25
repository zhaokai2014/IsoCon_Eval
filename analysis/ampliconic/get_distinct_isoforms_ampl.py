#!/usr/bin/env python

from __future__ import print_function
import os,sys
import argparse
import pickle
import subprocess
import re
import pysam 
from collections import defaultdict
import errno

from networkx import nx

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
except (ImportError, RuntimeError):
    print("COULD not import matplotlib")

import seaborn as sns
import pandas as pd


'''
    Below code taken from https://github.com/lh3/readfq/blob/master/readfq.py
'''

def readfq(fp): # this is a generator function
    last = None # this is a buffer keeping the last unprocessed line
    while True: # mimic closure; is it a bad idea?
        if not last: # the first record or a record following a fastq
            for l in fp: # search for the start of the next record
                if l[0] in '>@': # fasta/q header line
                    last = l[:-1] # save this line
                    break
        if not last: break
        name, seqs, last = last[1:].replace(" ", "_"), [], None
        for l in fp: # read the sequence
            if l[0] in '@+>':
                last = l[:-1]
                break
            seqs.append(l[:-1])
        if not last or last[0] != '+': # this is a fasta record
            yield name, ''.join(seqs), None # yield a fasta record
            if not last: break
        else: # this is a fastq record
            seq, leng, seqs = ''.join(seqs), 0, []
            for l in fp: # read the quality
                seqs.append(l[:-1])
                leng += len(l) - 1
                if leng >= len(seq): # have read enough quality
                    last = None
                    yield name, seq, ''.join(seqs); # yield a fastq record
                    break
            if last: # reach EOF before reading enough quality
                yield name, seq, None # yield a fasta record instead
                break


def reverse_complement(string):
    #rev_nuc = {'A':'T', 'C':'G', 'G':'C', 'T':'A', 'N':'N', 'X':'X'}
    # Modified for Abyss output
    rev_nuc = {'A':'T', 'C':'G', 'G':'C', 'T':'A', 'a':'t', 'c':'g', 'g':'c', 't':'a', 'N':'N', 'X':'X', 'n':'n', 'Y':'R', 'R':'Y', 'K':'M', 'M':'K', 'S':'S', 'W':'W', 'B':'V', 'V':'B', 'H':'D', 'D':'H', 'y':'r', 'r':'y', 'k':'m', 'm':'k', 's':'s', 'w':'w', 'b':'v', 'v':'b', 'h':'d', 'd':'h'}

    rev_comp = ''.join([rev_nuc[nucl] for nucl in reversed(string)])
    return(rev_comp)


def read_fasta_modify_header(fasta_file):
    fasta_seqs = {}
    k = 0
    temp = ''
    accession = ''
    for line in fasta_file:
        if line[0] == '>' and k == 0:
            accession = line[1:].strip().split()[0]
            accession = accession.replace("(","")
            accession = accession.replace(")","")
            accession = accession.replace(",","")
            accession = accession.replace("|","_")

            fasta_seqs[accession] = ''
            k += 1
        elif line[0] == '>':
            yield accession, temp
            temp = ''
            accession = line[1:].strip().split()[0]
            accession = accession.replace("(","")
            accession = accession.replace(")","")
            accession = accession.replace(",","")
            accession = accession.replace("|","_")
        else:
            temp += line.strip()
    yield accession, temp


def cs_to_cigar_and_ed(cs_string):
    errors = []
    # p = r"[=\+\-\~\*][A-Za-z]+"
    p = r"[=\+\-\*][A-Za-z]+|~[a-z]+[0-9]+[a-z]+"
    matches = re.findall(p, cs_string)
    # matches2 = re.findall(p2, cs_string)
    #occurences_by_type = {}
    # print("NEW")
    cigar_ext= ""
    ed = 0
    for i, t in enumerate(matches):
        # print(t)
        e_type = t[0]
        length = len(t[1:])
        # print(t)
        if e_type == "=":
            cigar_ext += "{0}{1}".format(length, "=")
        elif e_type == "~":
            length = int(t[3:-2])
            cigar_ext += "{0}{1}".format( length, "N")
            # ed += length
            # print(t, cs_string, matches, matches2)

        # here we store smaller errors/variations
        elif e_type == "*": # substitution
            cigar_ext += "{0}".format("*")
            ed += 1

        elif e_type == "-": # deletion
            cigar_ext += "{0}{1}".format(length, "D")
            ed += length

        elif e_type == "+": # insertion
            cigar_ext += "{0}{1}".format(length, "I")
            ed += length

        else: # reference skip or soft/hardclip "~", or match =
            print(t)
    # print(cigar_ext, ed)
    return cigar_ext, ed

# def is_isoform_match(cs_string):
    # errors = []
    # p = r"[=\+\-\*][A-Za-z]+|~[a-z]+[0-9]+[a-z]+"
    # matches = re.findall(p, cs_string)
    # ed = 0
    # for i, t in enumerate(matches):
    #     # print(t)
    #     e_type = t[0]
    #     # print(t)
    #     if e_type == "=":
    #         length = len(t[1:])
    #     elif e_type == "~":
    #         length = int(t[3:-2])
    #         ed += length
    #         if length >=5:
    #             return False
    #         # print(t, cs_string, matches, matches2)

    #     elif e_type == "*": # substitution
    #         ed += 1

    #     elif e_type == "-": # deletion
    #         length = len(t[1:])
    #         if length >=5:
    #             return False
    #         ed += length

    #     elif e_type == "+": # insertion
    #         length = len(t[1:])
    #         if length >=5:
    #             return False
    #         ed += length

    #     else: # reference skip or soft/hardclip "~", or match =
    #         print("UNEXPECTED!", t)
    #         sys.exit()


    # return True


# def print_out_tsv(nn_sequence_graph, best_exact_matches, reads, references, alignment_file, args):
#     tsv_file = open(os.path.join(args.outfolder, "all_matches.tsv"), "w")
#     tsv_file.write("predicted\treference\tedit_distance\tq_start_offset\tq_end_offset\tref_start_offset\tref_end_offset\tcs\n")
    
#     exact_file = open(os.path.join(args.outfolder, "exact_matches.tsv"), "w")
#     exact_file.write("predicted\treference\tq_len\tref_len\n")

#     isoform_file = open(os.path.join(args.outfolder, "isoform_matches.tsv"), "w")
#     isoform_file.write("predicted\treference\tedit_distance\tq_start_offset\tq_end_offset\tref_start_offset\tref_end_offset\tcs\n")

#     all_exact_matches = set()
#     all_isoform_matches = set()
#     reads_with_isoform_matches = set()

#     for q_acc in nn_sequence_graph:
#         for ref_acc in nn_sequence_graph[q_acc]:
#             read, cigar_ext, edit_distance = nn_sequence_graph[q_acc][ref_acc]
#             # cs_string = read.get_tag("cs")
#             # cigarstring = read.cigarstring

#             ref_start_offset = read.reference_start
#             ref_end_offset =  len(references[ref_acc]) - read.reference_end
#             q_start_offset =  read.query_alignment_start
#             q_end_offset =  len(reads[q_acc]) - read.query_alignment_end
#             if ref_start_offset == ref_end_offset == q_start_offset == q_end_offset == edit_distance == 0:
#                 # print("{0}\t{1}\t{2}\t{3}\t{4}\t{5}\t{6}\n".format(q_acc, ref_acc, edit_distance, q_start_offset, q_end_offset, ref_start_offset, ref_end_offset))
#                 exact_file.write("{0}\t{1}\t{2}\t{3}\n".format(q_acc, ref_acc, len(reads[q_acc]), len(references[ref_acc])))
#                 all_exact_matches.add(ref_acc)

#             if ref_start_offset <= 5 and ref_end_offset <= 5 and q_start_offset <= 5 and q_end_offset <= 5:
#                 cs_string = read.get_tag("cs")
#                 if is_isoform_match(cs_string):             
#                     # print("{0}\t{1}\t{2}\t{3}\t{4}\t{5}\t{6}\t{7}\n".format(q_acc, ref_acc, edit_distance, q_start_offset, q_end_offset, ref_start_offset, ref_end_offset, cigar_ext))
#                     isoform_file.write("{0}\t{1}\t{2}\t{3}\t{4}\t{5}\t{6}\t{7}\n".format(q_acc, ref_acc, edit_distance, q_start_offset, q_end_offset, ref_start_offset, ref_end_offset, cigar_ext))
#                     all_isoform_matches.add(ref_acc)
#                     reads_with_isoform_matches.add(q_acc)


#             # print(cs_string)
#             tsv_file.write("{0}\t{1}\t{2}\t{3}\t{4}\t{5}\t{6}\t{7}\n".format(q_acc, ref_acc, edit_distance, q_start_offset, q_end_offset, ref_start_offset, ref_end_offset, cigar_ext))

#     tsv_file.close()
#     exact_file.close()
#     isoform_file.close()
#     print("Unique exact matches:", len(all_exact_matches))
#     print("Unique isoform matches:", len(all_isoform_matches))

#     predictions_without_match = set(reads.keys()) - reads_with_isoform_matches
#     predictions_without_match_file = open(os.path.join(args.outfolder, "predictions_without_match.tsv"), "w")
#     for q_acc in predictions_without_match:
#         predictions_without_match_file.write("{0}\t{1}\n".format(q_acc, len(reads[q_acc])))
#     predictions_without_match_file.close()
#     print("Predictions without isoform match:", len(predictions_without_match))
#     print("total nr of predictions:", len(reads))


#     all_matches = set([ref_acc for q_acc in nn_sequence_graph for ref_acc in nn_sequence_graph[q_acc]])
#     no_hits = set(references.keys()) - all_matches
#     print("No hits:", len(no_hits), no_hits)
#     no_exact_hits = set(references.keys()) - all_exact_matches
#     for q_acc in nn_sequence_graph:
#         for ref_acc in no_exact_hits:
#             if ref_acc in nn_sequence_graph[q_acc]:
#                 read = nn_sequence_graph[q_acc][ref_acc][0]
#                 # print(nn_sequence_graph[q_acc][ref_acc][1], read.reference_start, len(references[ref_acc]) - read.reference_end, ref_acc)
#     print("No exact hits:", len(no_exact_hits), no_exact_hits)

#     return tsv_file.name


def get_exon_starts_and_stop(matches, first_exon_start):
    exon_coords = []
    ref_pos = first_exon_start
    
    current_exon_start = ref_pos
    for i, t in enumerate(matches):
        # print(t)
        e_type = t[0]
        # print(t)
        if e_type == "=":
            length = len(t[1:])
            ref_pos += length
        elif e_type == "~":
            current_exon_stop = ref_pos
            exon_coords.append( (current_exon_start, current_exon_stop) )

            length = int(t[3:-2])
            ref_pos += length
            current_exon_start = ref_pos
            # print(t)

        elif e_type == "*": # substitution
            ref_pos += 1

        elif e_type == "-": # deletion
            length = len(t[1:])
            ref_pos += length

        elif e_type == "+": # insertion
            length = len(t[1:])
            ref_pos += 0

        else: # reference skip or soft/hardclip "~", or match =
            print("UNEXPECTED!", t)
            sys.exit()

    #last exon
    current_exon_stop = ref_pos
    exon_coords.append( (current_exon_start, current_exon_stop) )

    return exon_coords


def get_exon_starts_and_stop_cigar(cigar_tuples, first_exon_start):
    exon_coords = []
    ref_pos = first_exon_start
    
    current_exon_start = ref_pos
    for i, (l,t) in enumerate(cigar_tuples):
        if t == "=" or t== "D" or  t== "M" or t == "X":
            ref_pos += l
        elif t == "N":
            current_exon_stop = ref_pos
            exon_coords.append( (current_exon_start, current_exon_stop) )
            ref_pos += l
            current_exon_start = ref_pos

        elif t == "I" or t == "S": # insertion or softclip
            ref_pos += 0

        else: # reference skip or soft/hardclip "~", or match =
            print("UNEXPECTED!", t)
            sys.exit()

    #last exon
    current_exon_stop = ref_pos
    exon_coords.append( (current_exon_start, current_exon_stop) )

    return exon_coords

def get_splice_sites(cigar_tuples, first_exon_start):
    splice_sites = []
    ref_pos = first_exon_start
    
    for i, (l,t) in enumerate(cigar_tuples):
        if t == "=" or t== "D" or  t== "M" or t == "X":
            ref_pos += l
        elif t == "N":
            splice_start = ref_pos
            ref_pos += l
            splice_stop = ref_pos

            splice_sites.append( (splice_start, splice_stop) )

        elif t == "I" or t == "S": # insertion or softclip
            ref_pos += 0

        else: # reference skip or soft/hardclip "~", or match =
            print("UNEXPECTED!", t)
            sys.exit()

    return splice_sites


def is_same_isoform_cigar_ampliconic(q_isoform, ref_isoform):
    # compare cs tag at intron sites
    q_cigar = q_isoform.cigarstring
    q_start = q_isoform.reference_start
    q_end = q_isoform.reference_end
    q_cigar_tuples = []
    result = re.split(r'[=DXSMIN]+', q_cigar)
    i = 0
    for length in result[:-1]:
        i += len(length)
        type_ = q_cigar[i]
        i += 1
        q_cigar_tuples.append((int(length), type_ ))

    ref_cigar = ref_isoform.cigarstring
    ref_start = ref_isoform.reference_start
    ref_end = ref_isoform.reference_end
    ref_cigar_tuples = []
    result = re.split(r'[=DXSMIN]+', ref_cigar)
    i = 0
    for length in result[:-1]:
        i += len(length)
        type_ = ref_cigar[i]
        i += 1
        ref_cigar_tuples.append((int(length), type_ ))
    
    # print(q_cigar_tuples)
    # print(ref_cigar_tuples)
    
    q_splice_sites = get_splice_sites(q_cigar_tuples, q_start)
    ref_splice_sites = get_splice_sites(ref_cigar_tuples, ref_start) 


    if len(q_splice_sites) == 0:
        if (ref_start <= q_start) and (q_end <= ref_end):
            return True
        else:
            # print(q_isoform.query_name, ref_isoform.query_name)
            # print(ref_start, q_start, q_end, ref_end)
            return False

    if q_isoform.query_name == "transcript_182_support_98_106_8.634747194009749e-192_747_S" and ref_isoform.query_name == "RBMY1B_ENST00000619219_ENSG00000242875_protein_coding":
        print(q_splice_sites, q_isoform.query_name)
        print(ref_splice_sites, ref_isoform.query_name)
        # sys.exit()

    # check if sorted list of splices (introns) is in the reference sorted list   
    nr_query_introns = len(q_splice_sites)
    nr_ref_introns = len(ref_splice_sites)
    if nr_query_introns > nr_ref_introns:
        return False
    else:
        for i in range(nr_ref_introns - nr_query_introns +1):
            if q_splice_sites == ref_splice_sites[i : i + nr_query_introns]:
                # print(q_splice_sites, q_isoform.query_name)
                # print(ref_splice_sites, ref_isoform.query_name)
                return True
    return False

def is_same_isoform_cigar_novel(q_isoform, ref_isoform):
    # compare cs tag at intron sites
    q_cigar = q_isoform.cigarstring
    q_start = q_isoform.reference_start
    q_end = q_isoform.reference_end
    q_cigar_tuples = []
    result = re.split(r'[=DXSMIN]+', q_cigar)
    i = 0
    for length in result[:-1]:
        i += len(length)
        type_ = q_cigar[i]
        i += 1
        q_cigar_tuples.append((int(length), type_ ))

    ref_cigar = ref_isoform.cigarstring
    ref_start = ref_isoform.reference_start
    ref_end = ref_isoform.reference_end
    ref_cigar_tuples = []
    result = re.split(r'[=DXSMIN]+', ref_cigar)
    i = 0
    for length in result[:-1]:
        i += len(length)
        type_ = ref_cigar[i]
        i += 1
        ref_cigar_tuples.append((int(length), type_ ))
    
    # print(q_cigar_tuples)
    # print(ref_cigar_tuples)
    
    q_splice_sites = get_splice_sites(q_cigar_tuples, q_start)
    all_q_splice_sites = set(q_splice_sites)
    ref_splice_sites = get_splice_sites(ref_cigar_tuples, ref_start) 

    if len(all_q_splice_sites) != len(ref_splice_sites):
        return False
    for r_start, r_stop in ref_splice_sites:
        if (r_start, r_stop) not in all_q_splice_sites:
            return False

    return True


def cigar_to_quality(q_isoform):
    cigarstring = q_isoform.cigarstring
    cigar_tuples = []
    result = re.split(r'[=DXSMIN]+', cigarstring)
    i = 0
    for length in result[:-1]:
        i += len(length)
        type_ = cigarstring[i]
        i += 1
        cigar_tuples.append((int(length), type_ ))
    
    unaligned = 0
    difference = 0
    for i, (l,t) in enumerate(cigar_tuples):
        if t == "=" or  t== "M":
            pass
        elif t== "D":
            difference += l
        elif t == "X":
            difference += l
        elif t == "N":
            pass
        elif t == "I":
            unaligned += l
            difference += l        
        elif t == "S": 
            unaligned += l
            difference += l

        else: # reference skip or soft/hardclip "~", or match =
            print("UNEXPECTED!", t)
            sys.exit()
    
    q_length = float(q_isoform.infer_query_length())

    alignment_id = (q_length - difference)/ q_length
    alignment_coverage = (q_length - unaligned)/q_length

    return alignment_id, alignment_coverage     

def pass_quality_filters(q_isoform):
    # ALIGNMENT_START = (147014079, 147014470)
    # ALIGNMENT_END = (147030158, 147030505)
    # check if all our transcripts fulfill the identity and coverage.
    ALIGN_COVERAGE = 0.99
    ALIGN_IDENTITY = 0.95
    if q_isoform.reference_name != "chrY":
        print("Wrong chromosome", q_isoform.reference_name, q_isoform.query_name)
        return False
    else:
        return True

    # alignment_id, alignment_coverage = cigar_to_quality(q_isoform)
    # if alignment_id < ALIGN_IDENTITY:
    #     print(q_isoform.query_name, "Below identity", alignment_id)  
    #     return False

    # if alignment_coverage < ALIGN_COVERAGE:
    #     print(q_isoform.query_name, "Below coverage", alignment_coverage)  
    #     return False

    # if not (ALIGNMENT_START[0] <= q_isoform.reference_start <= ALIGNMENT_START[1]):
    #     print(q_isoform.query_name, "Bad start", q_isoform.reference_start)  
    #     return False

    # if not (ALIGNMENT_END[0] <= q_isoform.reference_end <= ALIGNMENT_END[1]):
    #     print(q_isoform.query_name, "Bad end", q_isoform.reference_start) 
    #     return False

    return True

def detect_isoforms(ref_samfile_path, pred_samfile_path):

    ref_samfile = pysam.AlignmentFile(ref_samfile_path, "r", check_sq=False)
    pred_samfile = pysam.AlignmentFile(pred_samfile_path, "r", check_sq=False)

    # introns = pred_samfile.find_introns(pred_samfile.fetch(until_eof=True))
    # print(introns)
    # sys.exit()
    # ref_isoforms = [ref_isoform for ref_isoform in ref_samfile.fetch(until_eof=True)] 
    # query_isoforms = [q_isoform for q_isoform in pred_samfile.fetch(until_eof=True)]
    ref_isoforms = []
    prev_ref = ""
    for r_isoform in ref_samfile.fetch(until_eof=True):
        if r_isoform.query_name != prev_ref:
            ref_isoforms.append(r_isoform)
            prev_ref = r_isoform.query_name

    query_isoforms = []
    prev_query = ""
    for q_isoform in pred_samfile.fetch(until_eof=True):
        if q_isoform.query_name != prev_query:
            #apply quality filters such as: is aligned to chrX between start and end, has > 95% id and >=99% aligned bases
            if pass_quality_filters(q_isoform):
                query_isoforms.append(q_isoform)
            prev_query = q_isoform.query_name

    print(len(ref_isoforms), len(query_isoforms))

    counter_old = 0
    counter_new = 0
    ref_to_queries = { ref.query_name : set() for ref in ref_isoforms }
    queries_to_ref = { query.query_name : set() for query in query_isoforms }
    new_isoforms = set()

    for q_isoform in query_isoforms:
        is_new = True
        for ref_isoform in ref_isoforms:
            if is_same_isoform_cigar_ampliconic(q_isoform, ref_isoform):
                # print("YO")
                # print(q_isoform.query_name)
                # print(queries_to_ref)
                # print(queries_to_ref[q_isoform.query_name])
                queries_to_ref[q_isoform.query_name].add(ref_isoform.query_name)
                if len(queries_to_ref[q_isoform.query_name]) > 1:
                    print("More than 1 ref")
                    print("Same", q_isoform.query_name, queries_to_ref[q_isoform.query_name] )
                is_new = False
            
        if is_new:
            counter_new += 1
            print("New", q_isoform.query_name, q_isoform.cigarstring)
            new_isoforms.add(q_isoform.query_name)
            queries_to_ref[q_isoform.query_name] = ""

        else:
            # assert len(queries_to_ref[q_isoform.query_name]) == 1
            # if more than one hit, chiose lexocographically smallest
            counter_old += 1
            ref = sorted(queries_to_ref[q_isoform.query_name])[0]
            queries_to_ref[q_isoform.query_name] = ref

            ref_to_queries[ref].add(q_isoform.query_name)


    print([ len(ref_to_queries[r]) for r in ref_to_queries] )
    for r in sorted(ref_to_queries):
        print(len(ref_to_queries[r]), r)
    total_predictions = len(query_isoforms)
    print(total_predictions, "Total predictions")
    print(counter_old, "predictions had the same isoform structure as ref")
    print(counter_new, "predictions had new isoform structure to ref")
    
    ref_isoform_dict = { r.query_name : r for r in ref_isoforms}

    return queries_to_ref, new_isoforms, query_isoforms, ref_isoform_dict


def group_novel_isoforms(new_isoforms, all_filter_passing_query_isoforms, pred_samfile_path, outfile):
    pred_samfile = pysam.AlignmentFile(pred_samfile_path, "r", check_sq=False)
    query_new_isoforms = [q_isoform for q_isoform in all_filter_passing_query_isoforms if q_isoform.query_name in new_isoforms]
    G = nx.Graph()
    for n in new_isoforms:
        G.add_node(n)
    print("nr new:", len(query_new_isoforms))
    for i1 in query_new_isoforms:
        for i2 in query_new_isoforms:
            if i1.query_name == i2.query_name:
                continue
            else:
                if is_same_isoform_cigar_novel(i1, i2) and is_same_isoform_cigar_novel(i2, i1):
                    G.add_edge(i1.query_name, i2.query_name)

    print(len(list(G.nodes())))
    print(len(list(G.edges())))
    maximal_cliques = [cl for cl in nx.find_cliques(G)]


    print([ len(cl) for cl in maximal_cliques] )
    print(sum([ len(cl) for cl in maximal_cliques]) )
    print(len([ len(cl) for cl in maximal_cliques]), "unique splice sites isoforms")

    queries_to_new = { q_acc :  "new_isoform_"+str(i)  for i, cl in enumerate(sorted(maximal_cliques, key=len)) for q_acc in cl }
    return queries_to_new


def get_novelty(q_isoform, ref_isoform):
    # compare cs tag at intron sites
    q_cs_string = q_isoform.get_tag("cs")
    q_start = q_isoform.reference_start
    q_end = q_isoform.reference_end

    ref_cs_string = ref_isoform.get_tag("cs")
    ref_start = ref_isoform.reference_start
    ref_end = ref_isoform.reference_end
    
    errors = []
    p = r"[=\+\-\*][A-Za-z]+|~[a-z]+[0-9]+[a-z]+"
    
    q_matches = re.findall(p, q_cs_string)
    ref_matches = re.findall(p, ref_cs_string)    
    # print(q_start, q_end, ref_start, ref_end)

    q_exons = get_exon_starts_and_stop(q_matches, q_start)
    ref_exons = get_exon_starts_and_stop(ref_matches, ref_start)
    all_ref_exons = set(ref_exons)

    # print(len(all_q_exons), len(ref_exons))
    # if len(all_ref_exons) != len(q_exons):
    #     return None #("exon combination", len(all_q_exons))
    novelties = []
    for q_start, q_stop in q_exons:
        if (q_start, q_stop) not in all_ref_exons:
            novelties.append((q_start, q_stop))
            # if "transcript_846_" in q_isoform.query_name:            
            #     print(q_isoform.query_name, ref_isoform.query_name, r_start, r_stop, sorted(all_q_exons))
            #     print("start and end!", q_start, q_end, ref_start, ref_end)
            # print(False)

    return set(novelties)


def get_tag(diff_coords):
    exon_ranges = [ (147014219,147014282,9),
                    (147018023,147018132,10),
                    (147018985,147019119,11),
                    (147019618,147019680,12),
                    (147022095,147022181,13),
                    (147024651,147024846,14),
                    (147026389,147026571,15),
                    (147027054,147027136,16),
                    (147030203,147030451,17) ]
    tag = ""
    for q_start, q_stop in sorted(diff_coords):
        for i, (r_start, r_stop, exon_nr) in enumerate(exon_ranges):
            if exon_ranges[i-1][1] < q_start  and  q_stop < r_start:
                tag += "intron" + str(exon_nr) +";"

            elif r_start <= q_start <= r_stop or  r_start <= q_stop <= r_stop:
                tag += "exon" + str(exon_nr) + ";"
            elif q_start <= r_start and r_stop <= q_stop:
                tag += "exon" + str(exon_nr) + ";"
            elif r_start <= q_start and q_stop <= r_stop :
                tag += "exon" + str(exon_nr) + ";"

            # print(splice)
            # if r_start <= q_start <=  and r_stop <= q_stop:
            #     tag += 'spans' + str(exon_ranges[(r_start,r_stop)]) + "_{0}-{1};".format(q_start,q_stop)
            # elif r_start <= q_start and q_stop <= r_stop:
            #     tag += 'within' + str(exon_ranges[(r_start,r_stop)]) + ";"

            # elif r_start < q_start < r_stop and q_stop > r_stop:
            #     tag += '3"overlap' + str(exon_ranges[(r_start,r_stop)]) + ";"

    return tag


def get_novelty_feature(new_isoforms, pred_samfile_path, ref_samfile_path, outfile):
    pred_samfile = pysam.AlignmentFile(pred_samfile_path, "r", check_sq=False)
    ref_samfile = pysam.AlignmentFile(ref_samfile_path, "r", check_sq=False)

    novel_query_isoforms = [q_isoform for q_isoform in pred_samfile.fetch(until_eof=True) if q_isoform.query_name in new_isoforms]
    ref_isoforms = [ref_isoform for ref_isoform in ref_samfile.fetch(until_eof=True)] 
    features = {}
    for i1 in novel_query_isoforms:
        features[i1.query_name] = []
        
        temp_ = []
        for i2 in ref_isoforms:
            novelties_to_ref = get_novelty(i1, i2)
            if novelties_to_ref:
                temp_.append( novelties_to_ref )
                # print(novelties_to_ref, i1.query_name)
            # else:
            #     print("LOOOOL", temp_)
            #     sys.exit()
       
        # select minimal common difference to other isoform
        common_diffs = set.intersection( *temp_ )
        if not temp_:
            print()
            features[i1.query_name] = "exon_comb"
            print()            
        if common_diffs:
            print(common_diffs)
            tag = get_tag(common_diffs)
            print(tag)
            features[i1.query_name] = tag
        else:
            print()
            print(temp_)
            features[i1.query_name] = "splice_comb"
            print()
    return features
        # min_diff = 100
        # for t in temp_:
        #     if len(t[0]) < min_diff:
        #         min_diff = len(t[0])
        # print("min_diff:", min_diff)
        # minimal_diffs = [ t for t in temp_ if min_diff == len(t[0]) ]
        # print(minimal_diffs)
        # assert len(set([t[0] for t in minimal_diffs])) == 1
        # if temp_:
        #     features[q_acc] = 
        # else:
        #     features[q_acc] = "exon_or_intron_diff"
        # print("how many:", len(minimal_diffs), minimal_diffs)
        # features[i1.query_name].append(junction_novelty_to_ref)

    # sys.exit()
    # for q_acc in features.keys():
    #     if not features[q_acc]:
    #         print()
    #         print("EXON NOVELTY", q_acc)
    #         print()
    #         features[q_acc] = [("exon_or_intron_diff",)]
    #     else:
    #         pass
            # print(q_acc, features[q_acc])

    # unique_splices = {}
    # for q_acc in features:
    #     # print(q_acc)
    #     assert type(q_acc) is str 
    #     # print(features[q_acc])
    #     # print( type(set(features[q_acc])) )
    #     # print( set(features[q_acc]) )
    #     # assert set(features[q_acc]) is set
    #     unique_splices[q_acc] = set([ tup for item in features[q_acc] for tup in item ] )
    #     print(unique_splices[q_acc])
    # # unique_splices = { q_acc : set(features[q_acc]) for q_acc in features.keys() }



def cigar_to_seq(cigar, q_start, q_seq):
    cigar_tuples = []
    result = re.split(r'[=DXSMIN~]+', cigar)
    i = 0
    for length in result[:-1]:
        i += len(length)
        type_ = cigar[i]
        i += 1
        cigar_tuples.append((int(length), type_ ))

    q_index = q_start
    q_aln = []
    for length_ , type_ in cigar_tuples:
        if type_ == "=" or type_ == "X" or type_ == "M":
            q_aln.append(q_seq[q_index : q_index + length_])
            q_index += length_
        
        elif  type_ == "I" or type_ == "S":
            # insertion w.r.t. reference
            q_aln.append(q_seq[q_index: q_index + length_])
            #  only q_seq index change
            q_index += length_

        elif type_ == 'D' or type_ == "N" or type_ == "~":
            # deletion w.r.t. reference
            q_aln.append('-' * length_)
        
        else:
            print("error")
            print(cigar)
            sys.exit()

    return  "".join([s for s in q_aln])



def mkdir_p(path):
    print("creating", path)
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def sam_to_alignment_fasta(queries_to_ref, queries_to_new, all_filter_passing_query_isoforms, ref_isoforms, outfolder, query_fasta, ref_fasta):
    all_filter_passing_query_isoforms = { aln_object.query_name : aln_object for aln_object in all_filter_passing_query_isoforms}
    assert len(queries_to_ref) == len(all_filter_passing_query_isoforms)


    ref_ids = set([r for r in queries_to_ref.values() if r] )
    ref_outfolder = os.path.join(args.outfolder, "in_fmr_paper")
    mkdir_p(ref_outfolder)
    fa_files_to_known = { ref_id : open(os.path.join(ref_outfolder, ref_id + ".fa"), "w") for ref_id in ref_ids}

    new_ids = set(queries_to_new.values())
    ref_outfolder = os.path.join(args.outfolder, "novel")
    mkdir_p(ref_outfolder)
    fa_files_to_novel = { ref_id : open(os.path.join(ref_outfolder, ref_id + ".fa"), "w") for ref_id in new_ids}

    # print(len(query_fasta.keys()))   
    # print(set(query_fasta.keys()) - set(queries_to_ref.keys())  )
    # print(set(queries_to_ref.keys()) - set(query_fasta.keys()) )
    # for q in query_fasta:
    #     if "transcript_1026_support_2_4_7" in q:
    #         print(q)

    for ref_id in ref_ids:
        cigar = ref_isoforms[ref_id].cigarstring
        r_seq = ref_fasta[ref_id]
        r_start = ref_isoforms[ref_id].query_alignment_start
        r_aln = cigar_to_seq(cigar, r_start, r_seq)
        fa_files_to_known[ref_id].write( ">{0}\n{1}\n".format(ref_id, r_aln) )    

    for q_acc in queries_to_ref:
        q_seq = query_fasta[q_acc]
        cigar = all_filter_passing_query_isoforms[q_acc].cigarstring
        q_start = all_filter_passing_query_isoforms[q_acc].query_alignment_start
        q_aln = cigar_to_seq(cigar, q_start, q_seq)
        ref_id = queries_to_ref[q_acc]
        if not ref_id:
            ref_id = queries_to_new[q_acc]
            fa_files_to_novel[ref_id].write( ">{0}\n{1}\n".format(q_acc, q_aln) )
        else:
            fa_files_to_known[ref_id].write( ">{0}\n{1}\n".format(q_acc, q_aln) )




def merge_two_dicts(x, y):
    """Given two dicts, merge them into a new dict as a shallow copy."""
    z = x.copy()
    z.update(y)
    return z

def main(args):
    query_fasta = {acc : seq for acc, seq in read_fasta_modify_header(open(args.query_fasta,"r"))} 
    ref_fasta = {acc : seq for acc, seq in read_fasta_modify_header(open(args.ref_fasta,"r"))} 

    outfile = open(os.path.join(args.outfolder, args.prefix + ".fa"), "w")
    outfile.close()
    queries_to_ref, new_isoforms, all_filter_passing_query_isoforms, ref_isoforms = detect_isoforms(args.refsamfile, args.querysamfile)
    queries_to_new = group_novel_isoforms(new_isoforms, all_filter_passing_query_isoforms, args.querysamfile, outfile)
    # new_isoform_tags = get_novelty_feature(new_isoforms, args.querysamfile, args.refsamfile, outfile)


    sam_to_alignment_fasta(queries_to_ref, queries_to_new, all_filter_passing_query_isoforms, ref_isoforms, args.outfolder, query_fasta, ref_fasta)

    # for i in range(len(new_clusters)):
    #     diffs = [new_isoform_tags[q_acc] for q_acc in new_clusters[i]]
    #     print(diffs)
    #     assert len(set(diffs)) ==1
    #     # for q_acc in new_clusters[cl]:

    # for q_acc in new_isoform_tags:
    #     print(new_isoform_tags[q_acc])
    outfile = open( os.path.join(args.outfolder, args.prefix + ".tsv" ), "w" )
    for q_acc in queries_to_ref:
        ref = queries_to_ref[q_acc]
        if ref:
            outfile.write("{0}\t{1}\t{2}\n".format(q_acc, ref, args.prefix) )
    outfile.close()


    # nn_sequence_graph = best_matches_to_accession_graph(all_matches, acc_to_seq)
    # print_out_tsv(nn_sequence_graph, all_matches,  reads, references, alignment_file, args)
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Evaluate pacbio IsoSeq transcripts.")
    parser.add_argument('refsamfile', type=str, help='Samfile.')
    parser.add_argument('querysamfile', type=str, help='Samfile.')
    # parser.add_argument('predictions', type=str, help='Fasta file with only filtered isoform hits to FMR region (output of "filter_hits_on_hg19" script).')
    parser.add_argument('outfolder', type=str, help='outfolder.')  
    parser.add_argument('prefix', type=str, help='prefix to outfile.') 
    parser.add_argument('--query_fasta', type=str, help='fasta file with queries.')
    parser.add_argument('--ref_fasta', type=str, help='fasta file with references.')


    args = parser.parse_args()


    if len(sys.argv)==1:
        parser.print_help()
        sys.exit()
    if args.outfolder and not os.path.exists(args.outfolder):
        os.makedirs(args.outfolder)


    main(args)

    