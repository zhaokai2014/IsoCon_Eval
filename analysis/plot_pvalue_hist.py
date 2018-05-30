
import sys,os,argparse

try:
    # import matplotlib
    # matplotlib.use('agg')
    # import matplotlib.pyplot as plt
    import pylab as plt
    import seaborn as sns
    sns.set_palette("husl", desat=.6)
    sns.set(font_scale=1.6)
    plt.rcParams.update({'font.size': 12})
except:
    pass

def histogram(data, args, name='histogram.png', x='x-axis', y='y-axis', x_cutoff=None, title=None):
    X_SMALL = 6
    SMALL_SIZE = 8
    MEDIUM_SIZE = 10
    BIGGER_SIZE = 12

    plt.rc('font', size=SMALL_SIZE)          # controls default text sizes
    plt.rc('axes', titlesize=MEDIUM_SIZE)     # fontsize of the axes title
    plt.rc('axes', labelsize=SMALL_SIZE)    # fontsize of the x and y labels
    plt.rc('xtick', labelsize=X_SMALL)    # fontsize of the tick labels
    plt.rc('ytick', labelsize=X_SMALL)    # fontsize of the tick labels
    plt.rc('legend', fontsize=SMALL_SIZE)    # legend fontsize
    plt.rc('figure', titlesize=BIGGER_SIZE)  # fontsize of the figure title

    plt.xscale('log')
    fig, ax = plt.subplots(nrows=3, ncols=3)
    import numpy as np
    MIN, MAX = 1.0e-20 , 1.0 #max(data)
    bins=np.logspace(np.log10(MIN),np.log10(MAX), 20)

    # print(sorted(data))
    data_sorted = [(prefix, pvals) for (prefix, pvals) in data.items()]

    for i, ax in enumerate(ax.flatten()):
        prefix, p_values = data_sorted[i]
        data1 = [max(1.1e-20, p) for p in p_values if p > 0]
        data2 = [1.0e-20 for p in p_values if p == 0]

        ax.hist([data2, data1], bins=bins, label=['Not computed', ''], color=["#e74c3c", "#3498db"])
        ax.set_title(prefix)
        ax.set_xlabel(x)
        ax.set_ylabel(y)
        ax.set_xscale("log")
        # plt.gca().set_xscale("log")   

    plt.legend(loc='upper right')
    fig.tight_layout()

    # if title:
    #     plt.title(title)

    plt.savefig(os.path.join(args.outfolder, "Figure_S15.pdf"))
    plt.clf()

def read_fasta(fasta_file):
    fasta_seqs = {}
    k = 0
    temp = ''
    accession = ''
    for line in fasta_file:
        if line[0] == '>' and k == 0:
            accession = line[1:].strip()
            fasta_seqs[accession] = ''
            k += 1
        elif line[0] == '>':
            yield accession, temp
            temp = ''
            accession = line[1:].strip()
        else:
            temp += line.strip().upper()
    if accession:
        yield accession, temp


def main(args):
    if args.fasta:
        all_seqs = {}
        for fasta in args.fasta:
            path, prefix = os.path.split(fasta)
            prefix = prefix[:-3]
            candidate_dict = {acc : seq for acc, seq in read_fasta(open(fasta,"r"))} 
            all_seqs[prefix] = candidate_dict
    elif args.tsv:
        candidate_dict = {line.split()[0] : line.split()[1] for line in open(args.tsv,"r")} 

    data = {}
    for prefix in all_seqs:
        p_values = []
        candidate_dict =  all_seqs[prefix]
        for acc in candidate_dict:
            p_val = acc.split("_")[5]
            if p_val == "not":
                # pass
                p_values.append(0.0)
            else:
                p_values.append( float( acc.split("_")[5]) )
        data[prefix] = p_values


    # p_values = [float( acc.split("_")[5]) for acc in candidate_dict]
    histogram(data, args, title="P-value distributions", x="p-value", y="Count" )

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Evaluate pacbio IsoSeq transcripts.")
    parser.add_argument('--outfolder', type=str, help='outfolder.')  
    # parser.add_argument('prefix', type=str, help='prefix to outfile.') 
    parser.add_argument('--fasta', nargs= "+", type=str, help='fasta.')
    parser.add_argument('--tsv', type=str, help='tsv.') 


    args = parser.parse_args()


    if len(sys.argv)==1:
        parser.print_help()
        sys.exit()
    if args.outfolder and not os.path.exists(args.outfolder):
        os.makedirs(args.outfolder)


    main(args)
