#!/usr/bin/env python
import complete_profile as cpr
from msvcrt import getch #Only runs in Win, and only in cmd.exe

'''Interactive production of development ground truth.
By taking the union of document annotations for different runs
and judging for each annotation if it is correct for this document.
'''
def interactiveGroundTruth(document):
    extracted_statements = document.dev_truth['extracted']
    for st in sorted(extracted_statements):
        st_name = st.replace("~", ".") # mongo unescape
        print st_name, "(Correct? Yes ENTER | No SPACE)"
        correct = getch()
        if correct == "\x03": #catch control-c
            print "Skipping to next document\n"
            break
        elif correct == " ":
            print "**%s INCORRECT**\n" % st_name
        elif correct == "\r":
            print "**%s CORRECT**\n" % st_name
        else:
            print "Unrecognized Input '%s', assume:" % correct
            print "**%s CORRECT**\n" % st_name
        

if __name__ == '__main__' :

    # Load Documents from Mongo
    li_docs = cpr.loadDocuments({'origin': 'linkedin'}, cpr.LinkedInProfile)
    for doc in li_docs:
        print '\n\n', doc.title
        if hasattr(doc, 'dev_truth'):
            interactiveGroundTruth(doc)
