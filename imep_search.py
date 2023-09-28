import os
import os.path
import re
import subprocess
import sys
import urllib.parse
import uuid

#######################################################################################################
# Implements fuzzy search for the Index of Middle English Prose (http://imep.lib.cam.ac.uk/incipits/)
#######################################################################################################

NUM_CANDIDATES = 200
NUM_SELECTIONS = 20

SRLIM_DIR = '/tekstlab/imep/srilm-1.7.3/bin/i686-m64/'

#MODEL_DIR = '/tekstlab/imep/binary_models/incipits'
#MODEL_DIR = '/tekstlab/imep/models'
MODEL_DIR = '/tekstlab/imep/models/without_short'

ppl1_pattern = re.compile('ppl1=\s*(\S+)')

def application(environ, start_response):
    status = '200 OK'
    response_headers = [('Content-type', 'text/plain')]

    query_string = urllib.parse.unquote_plus(environ['QUERY_STRING'])
    m = re.match('query=(.+)&type=(.+)', query_string)
    if m:
        query = m.group(1)
        prose_type = m.group(2)
    else:
        status = '500 Internal Server Error'
        output = b"Missing query!"
        start_response(status, response_headers)
        return [output]

    query_id = uuid.uuid4()

    query_file = "/tmp/imep_query_{}.txt".format(query_id)
    query_model_file = "/tmp/imep_query_{}".format(query_id)

    # Separate the characters in the query by spaces and the words by '<w/>' tags, and write it to file
    with open(query_file, 'w', encoding='utf-8') as f:
        lines = map(lambda word: " ".join(word), re.sub('query=', '', query).split())
        query = "<w/> " + " <w/> ".join(lines) + " <w/>"

        #with open("/tmp/anders.txt", "a", encoding='utf-8') as f2:
        #    print(f'query: {query}', file=f2)

        nonevents_file = 'nonevents_explicits.text' if prose_type == 'explicit' else 'nonevents_incipits.text'
        with open('/tekstlab/imep/' + nonevents_file, 'r', encoding='utf-8') as nonevents:
            ignored = nonevents.readlines()
        # Replace all sequences from the nonevents.txt file by a single <w/>
        # (so that each replacement retains the word boundary for subsequent replacements)
        for iw in ignored:
            query = re.sub(iw.rstrip(), '<w/>', query, flags=re.I)
        # Finally, remove any sequences of multiple <w/> tags with a single one
        f.write(re.sub(r'<w/>(?:\s*<w/>)+', '<w/>', query))

    # In a single invocation, ngram is able to run several texts against a single language model, but not a single
    # text against several language models. Since invoking the program once for each of many thousand language
    # models takes a lot of time, we do it the other way first, i.e., create a model for the query text and run all
    # incipits against that single model. However, doing it that way yields inferior results, so we select the best
    # X candidates from that run and run the more accurate process (i.e., running the query text against each incipit
    # model) only on those to remove poor results.

    # First create a series of models from the query text
    #subprocess.run([SRLIM_DIR + 'ngram-count', '-order', '5', '-no-sos', '-no-eos', '-wbdiscount',
    #               '-text', query_file, '-lm', query_model_file], universal_newlines=True)
    subprocess.run([SRLIM_DIR + 'ngram-count', '-order', '5', '-no-sos', '-no-eos', '-wbdiscount',
                   '-text', query_file, '-lm', "{}_5.lm".format(query_model_file)], universal_newlines=True)
    subprocess.run([SRLIM_DIR + 'ngram-count', '-order', '4', '-no-sos', '-no-eos', '-wbdiscount',
                   '-text', query_file, '-lm', "{}_4.lm".format(query_model_file)], universal_newlines=True)
    subprocess.run([SRLIM_DIR + 'ngram-count', '-order', '3', '-no-sos', '-no-eos', '-wbdiscount',
                   '-text', query_file, '-lm', "{}_3.lm".format(query_model_file)], universal_newlines=True)
    subprocess.run([SRLIM_DIR + 'ngram-count', '-order', '2', '-no-sos', '-no-eos', '-wbdiscount',
                   '-text', query_file, '-lm', "{}_2.lm".format(query_model_file)], universal_newlines=True)
    subprocess.run([SRLIM_DIR + 'ngram-count', '-order', '1', '-no-sos', '-no-eos', '-wbdiscount',
                   '-text', query_file, '-lm', "{}_1.lm".format(query_model_file)], universal_newlines=True)

    # Then run all incipits against the query models
    process = subprocess.run([SRLIM_DIR + 'ngram', '-order', '5', '-no-sos', '-no-eos',
                             '-lm', '{}_5.lm'.format(query_model_file), '-lambda', '0.6',
                             '-mix-lm2', '{}_4.lm'.format(query_model_file), '-mix-lambda2', '0.45',
                             '-mix-lm3', '{}_3.lm'.format(query_model_file), '-mix-lambda3', '0.2',
                             '-mix-lm4', '{}_2.lm'.format(query_model_file), '-mix-lambda4', '0.04',
                             '-mix-lm5', '{}_1.lm'.format(query_model_file), '-mix-lambda5', '0.01',
                             '-debug', '1', '-ppl', '/tekstlab/imep/{}s.text'.format(prose_type)],
                             stdout=subprocess.PIPE, universal_newlines=True, encoding='UTF-8')

    output_lines = process.stdout.splitlines()
    all_chunks = [ output_lines[i:i + 4] for i in range(0, len(output_lines), 4) ]
    chunks = all_chunks[:len(all_chunks)-1]

    ent1 = re.compile('&thorn;')
    ent2 = re.compile('&eth;')
    ent3 = re.compile('&wynn;')
    ent4 = re.compile('&yogh;')
    ent5 = re.compile('&aelig;')

    def replace_entities(candidate):
        c = re.sub(ent1, 'þ', candidate)
        c = re.sub(ent2, 'ð', c)
        c = re.sub(ent3, 'ƿ', c)
        c = re.sub(ent4, 'ȝ', c)
        c = re.sub(ent5, 'æ', c)
        return c

    def process_chunk(chunk_number, chunk):
        ppl1 = re.search(ppl1_pattern, chunk[2]).group(1)

        if ppl1 == 'undefined':
            # If the perplexity is undefined, set it to be a really high number so it won't be selected
            ppl1 = '10000.0'

        return (chunk_number, ppl1)

    blank_pattern = re.compile('\s+')
    word_sep_pattern = re.compile('<w/>')

    # Checks the length of a line in incipits.text or explicits.text
    def long_enough(candidate):
        cleaned_text = re.sub(word_sep_pattern, ' ', re.sub(blank_pattern, '', replace_entities(candidate))).strip()
        if len(cleaned_text) < 15:
            #with open("/tmp/anders.txt", "a", encoding='utf-8') as f:
            #    print(f'cand: {candidate}, cleaned: AAA{cleaned_text}BBB', file=f)
            return False
        else: return True


    with open('/tekstlab/imep/{}s.text'.format(prose_type), 'r', encoding='utf-8') as f:
        incipit_lines = f.readlines()

    incipit_numbers_and_pp1s = [ process_chunk(chunk_index + 1, chunk)
                                    for (chunk_index, chunk) in enumerate(chunks)
                                    if long_enough(incipit_lines[chunk_index]) ]

    # Sort all incipits based on their ppl1 values from the reverse matching
    incipit_numbers_and_pp1s.sort(key=lambda elm: float(elm[1]))

    # Select the best candidates for use in the proper testing procedure
    candidates = incipit_numbers_and_pp1s[:NUM_CANDIDATES]

    #with open("/tmp/anders_log.txt", "w", encoding='utf-8') as external_file:
    #    print('reverse:', file=external_file)
    #    for candidate in candidates:
    #        print(candidate, file=external_file)
    #    external_file.close()

    # Get the number of incipits, which will also be the number (and db index) of the first explicit.
    # NOTE: Make sure there are no additional, empty lines in incipits.text!
    with open('/tekstlab/imep/incipits.text', 'r', encoding='utf-8') as f:
        first_explicit_number = len(f.readlines())

    # Now run the query text against each of the NUM_CANDIDATES incipits with the lowest perplexity value
    # in the reversed matching process above, and return the NUM_SELECTIONS ones with the lowest value
    # when we do the 'proper' matching.
    candidates_with_proper_pp1s = []
    for incipit_info in candidates:
        # If we are looking for explicits, we need to adjust the number by the offset of the first explicit in the database
        incipit_number = incipit_info[0] + first_explicit_number if prose_type == 'explicit' else incipit_info[0]

        # Don't try to run the query text against a model unless the model actually exists,
        # which is not the case for very short incipits/explicits (since they are not in fact actual incipits or explicits)
        if os.path.isfile('{}/{}_1.lm'.format(MODEL_DIR, incipit_number)):
            #process = subprocess.run([SRLIM_DIR + 'ngram', '-order', '5', '-lm', '{}/{}.bin.lm'.format(MODEL_DIR, incipit_number),
            #                         '-no-sos', '-no-eos', '-ppl', query_file],
            #                         stdout=subprocess.PIPE, universal_newlines=True, encoding='UTF-8')
            #process = subprocess.run([SRLIM_DIR + 'ngram', '-order', '5', '-lm', '{}/{}.lm'.format(MODEL_DIR, incipit_number),
            #                         '-no-sos', '-no-eos', '-ppl', query_file],
            #                         stdout=subprocess.PIPE, universal_newlines=True, encoding='UTF-8')
            process = subprocess.run([SRLIM_DIR + 'ngram', '-order', '5', '-no-sos', '-no-eos',
                                     '-lm', '{}/{}_5.lm'.format(MODEL_DIR, incipit_number), '-lambda', '0.60',
                                     '-mix-lm2', '{}/{}_4.lm'.format(MODEL_DIR, incipit_number), '-mix-lambda2', '0.45',
                                     '-mix-lm3', '{}/{}_3.lm'.format(MODEL_DIR, incipit_number), '-mix-lambda3', '0.2',
                                     '-mix-lm4', '{}/{}_2.lm'.format(MODEL_DIR, incipit_number), '-mix-lambda4', '0.04',
                                     '-mix-lm5', '{}/{}_1.lm'.format(MODEL_DIR, incipit_number), '-mix-lambda5', '0.01',
                                     '-ppl', query_file],
                                     stdout=subprocess.PIPE, universal_newlines=True, encoding='UTF-8')
            #with open("/tmp/anders.txt", "a", encoding='utf-8') as external_file:
            #    print(incipit_number, file=external_file)
            #    print(process.stdout.splitlines(), file=external_file)
            #    external_file.close()
            #if len(process.stdout.splitlines()) >= 2:
            m = re.search(ppl1_pattern, process.stdout.splitlines()[1])
            #with open("/tmp/anders.txt", "a", encoding='utf-8') as external_file:
            #    print(f'{incipit_number}, {m.group(1)}', file=external_file)
            #    external_file.close()
            # Append a tuple containing the incipit number and ppl1 value from the proper matching of the query text against this incipit
            candidates_with_proper_pp1s.append((incipit_number, m.group(1)))
     
    # Sort the candidates based on their proper ppl1 values
    candidates_with_proper_pp1s.sort(key=lambda elm: float(elm[1]))

    #with open("/tmp/anders2.txt", "w", encoding='utf-8') as external_file:
    #    for candidate in candidates_with_proper_pp1s:
    #        print(candidate, file=external_file)

    selected = list(map(lambda candidate: candidate[0], candidates_with_proper_pp1s))[:NUM_SELECTIONS]
    #step1_candidates_without_short = filter(lambda candidate: os.path.isfile('{}/{}_1.lm'.format(MODEL_DIR, candidate[0])), candidates)
    #selected = list(map(lambda candidate: candidate[0], step1_candidates_without_short))[:NUM_SELECTIONS]
    #selected = list(map(lambda candidate: candidate[0], candidates))[:NUM_SELECTIONS]

    output = bytes(",".join(map(lambda i: str(i), selected)), "utf-8")

    start_response(status, response_headers)

    os.remove(query_file)
    os.remove('{}_1.lm'.format(query_model_file))
    os.remove('{}_2.lm'.format(query_model_file))
    os.remove('{}_3.lm'.format(query_model_file))
    os.remove('{}_4.lm'.format(query_model_file))
    os.remove('{}_5.lm'.format(query_model_file))

    return [output]
