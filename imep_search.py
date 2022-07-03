import os
import re
import subprocess
import sys
import urllib.parse
import uuid

#######################################################################################################
# Implements fuzzy search for the Index of Middle English Prose (http://imep.lib.cam.ac.uk/incipits/)
#######################################################################################################

NUM_CANDIDATES = 100
NUM_SELECTIONS = 20

SRLIM_DIR = '/tekstlab/imep/srilm-1.7.3/bin/i686-m64/'

#MODEL_DIR = '/tekstlab/imep/binary_models/incipits'
MODEL_DIR = '/tekstlab/imep/models'

ppl1_pattern = re.compile('ppl1=\s*(\S+)')

def application(environ, start_response):
    status = '200 OK'
    response_headers = [('Content-type', 'text/plain')]

    query = urllib.parse.unquote_plus(environ['QUERY_STRING'])
    if len(query) == 0:
        status = '500 Internal Server Error'
        output = b"Missing query!"
        start_response(status, response_headers)
        return [output]

    query_id = uuid.uuid4()

    query_file = "/tmp/imep_query_{}.txt".format(query_id)
    query_model_file = "/tmp/imep_query_{}.lm".format(query_id)

    # Separate the characters in the query by spaces and the words by '<w>' tags, and write it to file
    with open(query_file, 'w') as f:
        lines = map(lambda word: " ".join(word), re.sub('query=', '', query).split())
        query = "<w> " + " <w> ".join(lines) + " <w>"
        f.write(query)

    # In a single invocation, ngram is able to run several texts against a single language model, but not a single 
    # text against several language models. Since invoking the program once for each of many thousand language
    # models takes a lot of time, we do it the other way first, i.e., create a model for the query text and run all 
    # incipits against that single model. However, doing it that way yields inferior results, so we select the best
    # X candidates from that run and run the more accurate process (i.e., running the query text against each incipit
    # model) only on those to remove poor results.

    # First create a model from the query text
    subprocess.run([SRLIM_DIR + 'ngram-count', '-order', '5', '-no-sos', '-no-eos', '-wbdiscount', 
                   '-text', query_file, '-lm', query_model_file], universal_newlines=True)

    # Then run all incipits against the query model
    process = subprocess.run([SRLIM_DIR + 'ngram', '-order', '5', '-lm', query_model_file,
                             '-no-sos', '-no-eos', '-debug', '1', '-ppl', '/tekstlab/imep/incipits.text'], 
                             stdout=subprocess.PIPE, universal_newlines=True, encoding='UTF-8')

    output_lines = process.stdout.splitlines()
    all_chunks = [ output_lines[i:i + 4] for i in range(0, len(output_lines), 4) ]
    chunks = all_chunks[:len(all_chunks)-1]

    def process_chunk(chunk_number, chunk):
        ppl1 = re.search(ppl1_pattern, chunk[2]).group(1)

        if ppl1 == 'undefined': 
            # If the perplexity is undefined, set it to be a really high number so it won't be selected
            ppl1 = '10000.0'

        return (chunk_number, ppl1)

    incipit_numbers_and_pp1s = [ process_chunk(chunk_index + 1, chunk) for (chunk_index, chunk) in enumerate(chunks) ]

    # Sort all incipits based on thei ppl1 values from the reverse matching
    incipit_numbers_and_pp1s.sort(key=lambda elm: float(elm[1]))

    # Select the best candidates for use in the proper testing procedure
    candidates = incipit_numbers_and_pp1s[:NUM_CANDIDATES]

    #with open("/tmp/anders_log.txt", "w") as external_file:
    #    print('reverse:', file=external_file)
    #    for candidate in candidates:
    #        print(candidate, file=external_file)
    #    external_file.close()

    # Now run the query text against each of the NUM_CANDIDATES incipits with the lowest perplexity value
    # in the reversed matching process above, and return the NUM_SELECTIONS ones with the lowest value
    # when we do the 'proper' matching.
    candidates_with_proper_pp1s = []
    for incipit_info in candidates:
        incipit_number = incipit_info[0]
        #process = subprocess.run([SRLIM_DIR + 'ngram', '-order', '5', '-lm', '{}/{}.bin.lm'.format(MODEL_DIR, incipit_number),
        #                         '-no-sos', '-no-eos', '-ppl', query_file], 
        #                         stdout=subprocess.PIPE, universal_newlines=True, encoding='UTF-8')
        process = subprocess.run([SRLIM_DIR + 'ngram', '-order', '5', '-lm', '{}/{}.lm'.format(MODEL_DIR, incipit_number),
                                 '-no-sos', '-no-eos', '-ppl', query_file], 
                                 stdout=subprocess.PIPE, universal_newlines=True, encoding='UTF-8')
        #with open("/tmp/anders.txt", "a") as external_file:
        #    print(incipit_number, file=external_file)
        #    print(process.stdout.splitlines(), file=external_file)
        #    external_file.close()
        #if len(process.stdout.splitlines()) >= 2:
        m = re.search(ppl1_pattern, process.stdout.splitlines()[1])
        #with open("/tmp/anders.txt", "a") as external_file:
        #    print(f'{incipit_number}, {m.group(1)}', file=external_file)
        #    external_file.close()
        # Append a tuple containing the incipit number and ppl1 value from the proper matching of the query text against this incipit
        candidates_with_proper_pp1s.append((incipit_number, m.group(1)))
        
    # Sort the candidates based on their proper ppl1 values
    candidates_with_proper_pp1s.sort(key=lambda elm: float(elm[1]))

    #print('proper:')
    #for candidate in candidates_with_proper_pp1s:
    #    print(candidate)

    selected = list(map(lambda candidate: candidate[0], candidates_with_proper_pp1s))[:NUM_SELECTIONS]

    output = bytes(",".join(map(lambda i: str(i), selected)), "utf-8")

    start_response(status, response_headers)

    os.remove(query_file)
    os.remove(query_model_file)

    return [output]
