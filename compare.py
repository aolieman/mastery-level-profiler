#! /usr/bin/env python
import json
from spotlight import annotate
from functools import partial

def readVocabulary(infile):
    ifile = open(infile, 'rb')
    return json.load(ifile)

def getTermIDs(vocabulary):
    term_ids = set()
    for term in vocabulary:
        if u'more_wiki' in term:
            term_id = term[u'more_wiki'].split('/')[-1]
            term_ids.add(term_id)
    return term_ids

def throughSpotlight(text):
    api = partial(annotate, 'http://spotlight.dbpedia.org/rest/annotate',
                  confidence=0.0, support=0,
                  spotter='Default')
    annotations = api(text)
    annotation_ids = []
    for ann in annotations:
        annotation_ids.append(ann[u'URI'].split('/')[-1])
    return annotation_ids

if __name__ == '__main__' :

    vocabulary = readVocabulary('vocabulary_wsp.json')
    term_ids = getTermIDs(vocabulary)
    print len(term_ids)

    text = 'Librio is a service in the form of a web application which started out with the aim to make lending and trading books attractive to students. In the summer of 2011 a pilot study was conducted with students at the Delft University of Technology. This pilot led to the decision to aim for a broader audience of readers. Our plan for the coming year is to focus on "Librio Labs", a series of experiments that will be conducted with prototype versions of a new social cataloging application.'
    ann_ids = throughSpotlight(text)
    print ann_ids, '\nIntersecting with vocabulary...'
    print set(ann_ids).intersection(term_ids)
