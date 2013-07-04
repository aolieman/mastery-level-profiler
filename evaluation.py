#!/usr/bin/env python
import complete_profile as cpr
import compare
import nltk, heapq
from msvcrt import getch #Only runs in Win, and only in cmd.exe

# Load the en_uri -> topic_name translation dict
vocabulary = compare.readVocabulary('vocabulary_man.json')
term_ids, nl_dict, en_dict = compare.getTermIDs(vocabulary)

'''Interactive production of development ground truth.
By taking the union of document annotations for different runs
and judging for each annotation if it is correct for this document.
'''
def interactiveGroundTruth(document):
    print '\n\n', doc.title
    extracted_statements = document.dev_truth['extracted']
    init_length = countStatements(document, key='extracted')
    print "For each ann_id: Correct? Yes ENTER | No SPACE"
    for st in sorted(extracted_statements):
        st_id = st.replace("~", ".") # mongo unescape
        print en_dict[st_id].ljust(35) + st_id
        correct = getch()
        if correct == "\x03": #catch control-c
            print "Skipping to next document\n"
            break
        elif correct == " ":
            del extracted_statements[st]
            print "**%s REMOVED**\n" % st_id
        elif correct == "\r":
            print "**%s CORRECT**\n" % st_id
        else:
            print "Unrecognized Input '%s', assume:" % correct
            print "**%s CORRECT**\n" % st_id
    # Done; save document to mongo
    final_length = countStatements(document, key='extracted')
    print "\n %i incorrect statements were removed" % (init_length - final_length,)
    document.toMongo()

# Compute length of a statements dict of a document
def countStatements(document, key='extracted'):
    if hasattr(document, 'dev_truth'):
        return len(document.dev_truth[key])
    else: return 0

# Find if a term exists in the vocabulary as id or name
def is_candidate(term):
    if term in en_dict:
        print term, en_dict[term]
    elif term in en_dict.itervalues():
        print "???", term
    elif term in en_dict[None]:
        print None, term
    else: print "nope"

# Computes the Edit Ratio [0-1] metric between two strings
# Can perhaps also be used to find missing URIs in the vocabulary
def edit_ratio(str1, str2):
    distance = nltk.metrics.edit_distance(str1, str2)
    return float(distance) / max(len(str1), len(str2))

# Judge two LinkedIn docs and remove dev_truth from non-judged docs
def judgeLinkedIn():
    # Load LinkedIn Documents from Mongo
    li_docs = cpr.loadDocuments({'origin': 'linkedin'}, cpr.LinkedInProfile)
    # Select the two docs with most extracted statements
    two_most = heapq.nlargest(2, li_docs, key=countStatements)
##    for doc in two_most:
##        if countStatements(doc, key='extracted') > 0:
##            interactiveGroundTruth(doc)
##        else: print "Max statements is 0; Check documents!"
    # Remove 'dev_truth' from the non-judged documents (prompt to be sure)
    for doc in li_docs:
        if doc not in two_most:
            print "Delete dev_truth for %s? YES or NO" % doc.title
            delete = raw_input('Delete?-> ')
            if delete == "YES":
                del doc.dev_truth
                doc.toMongo()
            else: print doc.title, "skipped"


if __name__ == '__main__' :

    #judgeLinkedIn()

    # Some is_candidate tests
    is_candidate("Design") # should be in en_dict
    is_candidate("Architecting") # should be in en_dict[None]
    is_candidate("Arab-Israeli_Conflict") # not linked
    is_candidate("Food Photography") # should be in en_dict.values
    
    # Some edit_ratio tests
    print "AP", "APV", edit_ratio("AP", "APV")
    print "XML", "APV", edit_ratio("XML", "APV")
    print "Architecting", "Architecting", edit_ratio("Architecting", "Architecting")
    # Easy matching
    print 'Food Photography', 'Food_photography', edit_ratio('Food Photography', 'Food_photography')
    # Disamgiguation suffix needs to be stripped?
    print "Python", "Python_(programming_language)", edit_ratio("Python", "Python_(programming_language)")
