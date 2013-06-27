#! /usr/bin/env python
import json
from spotlight import annotate, SpotlightException
from functools import partial

def readVocabulary(infile):
    ifile = open(infile, 'rb')
    return json.load(ifile)

def getTermIDs(vocabulary):
    term_ids = set()
    translations = dict()
    for term in vocabulary:
        if u'more_wiki' in term:
            term_id = term[u'more_wiki'].split('wiki/')[-1]
            term_ids.add(term_id)
        if u'nl_uri' in term:
            term_nlid = term[u'nl_uri'].split('resource/')[-1]
            term_ids.add(term_nlid)
            translations[term_nlid] = (term_id, term['name'])
    return term_ids, translations

def throughSpotlight(text, conf=0.0, supp=0, lang='en'):
    en_sztaki = 'http://spotlight.sztaki.hu:2222/rest/annotate'
    en_default = 'http://spotlight.dbpedia.org/rest/annotate' #try KeyphraseSpotter
    en_local = 'http://localhost:2222/rest/annotate'
    nl_default = 'http://nl.dbpedia.org/spotlight/rest/annotate'
    nl_local = 'http://localhost:2223/rest/annotate'
    api = partial(annotate, en_sztaki,
                  confidence=conf, support=supp,
                  spotter='Default')
    if lang == 'nl':
        api = partial(annotate, nl_local,
                  confidence=conf, support=supp,
                  spotter='Default')
    try:
        spotlight_response = api(text)
    except SpotlightException, err:
        print err
        return None
    annotation_ids = []
    for ann in spotlight_response:
        annotation_ids.append(ann[u'URI'].split('resource/')[-1])
    return annotation_ids, spotlight_response

if __name__ == '__main__' :

    vocabulary = readVocabulary('vocabulary_man.json')
    term_ids, trans_dict = getTermIDs(vocabulary)
    print len(term_ids)

    text = 'Librio is a service in the form of a web application which started out with the aim to make lending and trading books attractive to students. In the summer of 2011 a pilot study was conducted with students at the Delft University of Technology. This pilot led to the decision to aim for a broader audience of readers. Our plan for the coming year is to focus on "Librio Labs", a series of experiments that will be conducted with prototype versions of a new social cataloging application.'
    ann_ids, resp = throughSpotlight(text)
    print resp
    print ann_ids, '\nIntersecting with vocabulary...'
    print set(ann_ids).intersection(term_ids)
