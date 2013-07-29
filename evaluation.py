#!/usr/bin/env python
import complete_profile as cpr
import dev_format as ft
import compare
import nltk, heapq, numpy, csv
from msvcrt import getch #Only runs in Win, and only in cmd.exe

# Load the en_uri -> topic_name translation dict
vocabulary = compare.readVocabulary('vocabulary_man.json')
term_ids, nl_dict, en_dict, en_summary = compare.getTermIDs(vocabulary)

'''Interactive production of development ground truth.
By taking the union of document annotations for different runs
and judging for each annotation if it is correct for this document.
'''
def interactiveGroundTruth(document):
    try:
        print document.title
    except AttributeError:
        print document._id
    extracted_statements = document.dev_truth['extracted']
    init_length = countStatements(document, key='extracted')
    print "For each ann_id: Correct? Yes ENTER | No SPACE"
    for st in sorted(extracted_statements):
        st_id = st.replace("~", ".") # mongo unescape
        try:
            print en_dict[st_id].ljust(35) + st_id
        except KeyError:
            del extracted_statements[st]
            print "*%s is not in current vocabulary*" % st_id
            print "**%s REMOVED**\n" % st_id
            continue
        except UnicodeEncodeError:
            try:
                old_st_id = st_id
                st_id = st_id.encode('cp850', errors='replace')
                #TODO: encoding works in test, but gets messed by concat?
                print en_dict[st_id].ljust(35) + st_id
            except:
                st_id = repr(st_id)                
                print "*%s or %s cannot be printed*" % (st_id,
                                                        repr(en_dict[old_st_id]))
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
    print "\n %i incorrect statements were removed\n" % (init_length - final_length,)
    document.toMongo()
    return init_length - final_length

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

def is_candidateTests():
    # Some is_candidate tests
    is_candidate("Design") # should be in en_dict
    is_candidate("Architecting") # should be in en_dict[None]
    is_candidate("Arab-Israeli_Conflict") # not linked
    is_candidate("Food Photography") # should be in en_dict.values

# Computes the Edit Ratio [0-1] metric between two strings
# Can perhaps also be used to find missing URIs in the vocabulary
def edit_ratio(str1, str2):
    distance = nltk.metrics.edit_distance(str1, str2)
    return float(distance) / max(len(str1), len(str2))

def edit_ratioTests():
    # Some edit_ratio tests
    print "AP", "APV", edit_ratio("AP", "APV")
    print "XML", "APV", edit_ratio("XML", "APV")
    print "Architecting", "Architecting", edit_ratio("Architecting", "Architecting")
    # Easy matching
    print 'Food Photography', 'Food_photography', edit_ratio('Food Photography', 'Food_photography')
    # Disamgiguation suffix needs to be stripped?
    print "Python", "Python_(programming_language)", edit_ratio("Python", "Python_(programming_language)")

# Judge two LinkedIn docs and remove dev_truth from non-judged docs
def judgeLinkedIn():
    # Load LinkedIn Documents from Mongo
    li_docs = cpr.loadDocuments({'origin': 'linkedin'}, cpr.LinkedInProfile)
    # TODO: docs need statements in dev_truth['extracted']
    # Select the two docs with most extracted statements and judge them
    two_most = heapq.nlargest(2, li_docs, key=countStatements)
    for sel_doc in two_most:
        if countStatements(sel_doc, key='extracted') > 0:
            interactiveGroundTruth(sel_doc)
        else: print "Max statements is 0; Check documents!"
    # Remove 'dev_truth' from the non-judged documents (prompt to be sure)
    for doc in li_docs:
        if doc not in two_most:
            print "Delete dev_truth for %s? YES or NO" % doc.title
            delete = raw_input('Delete?-> ')
            if delete == "YES":
                del doc.dev_truth
                doc.toMongo()
            else: print doc.title, "skipped"

def judgeCourseDescriptions():
    # Which courses were taken by many students?
    c_dict, top = countCourseAttendance()
    (top_nl, top_en) = [], []
    for c_id, count in top:
        doc = cpr.loadDocuments({'_id': c_id})[0]
        if doc.language == 'en':
            top_en.append(doc)
        elif doc.language == 'nl':
            top_nl.append(doc)
        if min(len(top_en), len(top_nl)) >= 3:
            break # 3 top docs per language is enough
    # Make statements and judge selected docs
    for sel_doc in (top_nl[0], top_nl[0]):
        print "\n\n", sel_doc._id
        if hasattr(sel_doc, 'dev_truth'):
            print "Overwrite dev_truth for %s? YES or NO" % sel_doc._id
            overwrite = raw_input('Overwrite?-> ')
            if overwrite == "YES": pass
            else:
                print sel_doc._id, "skipped"
                continue
        
        sel_doc.dev_truth = {}
        sel_doc.makeStatements("dev_truth") # should work, but verify
        interactiveGroundTruth(sel_doc)

def countCourseAttendance():
    count_dict = {}
    year_dict = {u'total': 0}
    for y in xrange(2004, 2013):
        year_dict[unicode(y)] = 0
    profiles = cpr.loadProfiles()
    for p in profiles:
        if p.tudelft == None: continue
        for c in p.tudelft:
            c_code = c['cursusid']
            c_year = c['collegejaar']
            if c_code not in count_dict:
                count_dict[c_code] = year_dict.copy()
            count_dict[c_code][c_year] += 1
            count_dict[c_code][u'total'] += 1
    top = sorted([("%sy%s" % (key, maxYear(value)), value[u'total'])
                  for key, value in count_dict.iteritems()
                  if value[u'total'] > 5],
                  key=lambda tup: tup[1], reverse=True)
    return count_dict, top

def maxYear(y_dict):
    for y in xrange(2012, 2004, -1):
        if (y_dict[unicode(y)] > 0
        and y_dict[unicode(y)] >= y_dict[unicode(y-1)]):
            return unicode(y)

# Judge three Shareworks docs and remove dev_truth from non-judged docs
def judgeShareworksPortfolio():
    # Load Shareworks Documents from Mongo
    posts = cpr.loadDocuments({'doctype': 'posts'})
    reports = cpr.loadDocuments({'doctype': 'report'})
    slides = cpr.loadDocuments({'doctype': 'slides'})
    # Make statements for all sw_docs
    has_dev_truth_count = 0
    overwrite = False
    while True: # this loop is a strange hack and needs refactoring
        print "\nMaking statements for sw_docs (overwrite=%s)" % overwrite
        if has_dev_truth_count < 0:
            has_dev_truth_count = -67
        for doc in (posts + reports + slides):
            # threshold for overwriting dev_truths
            if has_dev_truth_count > 10:
                print "\nAssuming docs are not judged; overwrite everything"
                overwrite = True
                has_dev_truth_count = -1
                break                
            if hasattr(doc, 'dev_truth') and not overwrite:
                has_dev_truth_count += 1
                print "!!%s already has a dev_truth; skipping" % doc._id
                continue # don't overwrite; might be judged already
            doc.dev_truth = {}
            doc.makeStatements()
        if not overwrite or has_dev_truth_count < -10:
            print "\nDone making statements!"
            break
    # Select the post closest to 15th percentile # of extracted statements
    post_counts = map(countStatements, posts)
    perc_15 = 1/numpy.percentile(post_counts, 15.0)
    sel_post = min(posts,
	       key=lambda d: abs(countStatements(d)*perc_15-1))
    print "\nPost %s selected (%i statements)" % (sel_post._id,
                                                  countStatements(sel_post))
    # Select the report closest to median # of extracted statements
    report_counts = map(countStatements, reports)
    perc_50 = 1/numpy.percentile(report_counts, 50.0)
    sel_report = min(reports,
	       key=lambda d: abs(countStatements(d)*perc_50-1))
    print "\nReport %s selected (%i statements)" % (sel_report._id,
                                                  countStatements(sel_report))
    # Select the slides closest to median # of extracted statements
    # (use a sort here, because there aren't too many slides docs)
    sel_slides = sorted(slides, key=countStatements)[len(slides)/2]
    print "\nSlides %s selected (%i statements)" % (sel_slides._id,
                                                  countStatements(sel_slides))

    # Judge the selected documents
    for sel_doc in (sel_post, sel_report, sel_slides):
        if countStatements(sel_doc, key='extracted') > 0:
            interactiveGroundTruth(sel_doc)
        else: print "Can't judge a doc with 0 statements; Check documents!"

    # Remove 'dev_truth' from the non-judged documents
    for doc in (posts + reports + slides):
        if doc not in (sel_post, sel_report, sel_slides):
            #print "Delete dev_truth for %s" % doc._id
            del doc.dev_truth
            doc.toMongo()
        else: print doc._id, "dev_truth kept!"
    print "\nAll dev_truths deleted for non-judged documents"

# Judge three website docs (and remove dev_truth from non-judged docs)
def judgeWebsites():
    # Load website Documents from Mongo
    ws_docs = cpr.loadDocuments({'origin': 'website'})
    # Make statements for all ws_docs
    for doc in ws_docs:
        if hasattr(doc, 'dev_truth'):
            print "Not making statements for %s; already has dev_truth" % doc.title
        else:
            doc.dev_truth = {}
            doc.makeStatements()
    # Select two docs with most statements
    two_most = heapq.nlargest(2, ws_docs, key=countStatements)
    # Remove dev_truth for non-selected docs
    for doc in ws_docs:
        if doc not in two_most:
            print "Delete dev_truth for %s" % doc.title
            del doc.dev_truth
            doc.toMongo()
    # Judge selected docs
    for sel_doc in two_most:
        if countStatements(sel_doc, key='extracted') > 0:
            rm_count = interactiveGroundTruth(sel_doc)
            if rm_count < 1:
                print("No statements removed: default behavior DELETE.\n"
                      "Press Enter or Space to KEEP dev_truth,"
                      " or another key to delete ...")
                delete = getch()
                if delete in (" ", "\r"):
                    print "**Dev_truth KEPT**\n"
                else:
                    del sel_doc.dev_truth
                    print "**Dev_truth DELETED**\n"
        else: print "Max statements is 0; Check documents!"

# Make statements for docs with dev_truth
def devStatements(dev_docs, dev_runs, verbose=0):
    for doc in dev_docs:
        for run_str in dev_runs:
            if verbose > 0:
                print "\nStatements for doc %s, run %s:" % (doc._id, run_str)
            doc.makeStatements(run_str, del_resp=True)
            run_stmts = getattr(doc, run_str, None)
            if not run_stmts: continue
            if verbose > 1: print run_stmts['extracted'].keys()
    return dev_docs, dev_runs

# Precision: fraction of correct generated statements
# Recall: fraction of statements in truth that have been generated
# inputs: statements produced by run, statements in truth
def performance(generated, truth, beta=1):
    correct = set(truth).intersection(set(generated))
    incorrect = set(generated).difference(set(truth))
    missing = set(truth).difference(set(generated))

    try:
        precision = len(correct) / float(len(generated))
    except ZeroDivisionError:
        precision = 0 # no statments were generated in this run
    recall = len(correct) / float(len(truth))
    f_beta, f_str = f_score(precision, recall, beta)

    results = {'correct': correct,
               'incorrect': incorrect,
               'missing': missing,
               'precision': precision,
               'recall': recall,
               f_str: f_beta}
    
    return results

def f_score(precision, recall, beta):
    if not precision and not recall:
        score = 0
    else:
        score = (1+beta**2)*(precision*recall)/((beta**2*precision)+recall)
    return score, "F%s" % beta

def docRunEvalTable(dev_docs, dev_runs):
    # Print table of performance per document / run
    rows = []
    header = ["Doc_ID", "lang"] + dev_runs
    for doc in dev_docs:
        row = [doc._id, doc.language]
        for runstr in dev_runs:
            run = getattr(doc, runstr, None) # not tested yet
            if not run: continue
            extracted = run['extracted']
            truth = doc.dev_truth['extracted']
            res = performance(extracted, truth)
            resstr = "p %.2f, r %.2f" % (res['precision'], res['recall'])
            row.append(resstr)
        rows.append(row)
    print ft.matrix_to_string(rows, header)

def truthPerLanguage(dev_docs):
    nl_truth, en_truth = set(), set()
    nl_docs, en_docs = [], []
    for doc in dev_docs:
        if doc.language == 'nl':
            nl_truth.update(doc.dev_truth['extracted'])
            nl_docs.append(doc)
        elif doc.language == 'en':
            en_truth.update(doc.dev_truth['extracted'])
            en_docs.append(doc)
    return (nl_truth, en_truth), (nl_docs, en_docs)

def extractedPerLanguage(nl_docs, en_docs, runstr):
    extracted_nl, extracted_en = set(), set()
    for doc in nl_docs:
        run = getattr(doc, runstr, None)
        if not run: continue
        extracted_nl.update(run['extracted'])
    for doc in en_docs:
        run = getattr(doc, runstr, None)
        if not run: continue
        extracted_en.update(run['extracted'])
    return extracted_nl, extracted_en

def runLangEvalTable(dev_docs, dev_runs):
    # Print table of performance per run / language
    rows = []
    header = ["Run", "Dutch", "English"]
    (nl_truth, en_truth), (nl_docs, en_docs) = truthPerLanguage(dev_docs)
    for runstr in dev_runs:
        row = [runstr]
        extracted_nl, extracted_en = extractedPerLanguage(nl_docs, en_docs,
                                                          runstr)
        if len(nl_truth) > 0:
            nl_res = performance(extracted_nl, nl_truth)
            row.append("p %.2f, r %.2f" % (nl_res['precision'], nl_res['recall']))
        else: row.append("none")
        if len(en_truth) > 0:
            en_res = performance(extracted_en, en_truth)
            row.append("p %.2f, r %.2f" % (en_res['precision'], en_res['recall']))
        else: row.append("none")
        rows.append(row)
    print ft.matrix_to_string(rows, header)

def csvEvalTable(dev_docs, dev_runs):
    # Save a CSV table of performance at different runs
    beta = 0.5
    f_str = "F%s" % beta
    header = ["Run", "Precision", "Recall", f_str, "Lang", "Cand"]
    with open('csv_output/EvalTable.tab', 'wb') as tsvfile:
        wr = csv.writer(tsvfile, delimiter="\t")
        wr.writerow(header)
        (nl_truth, en_truth), (nl_docs, en_docs) = truthPerLanguage(dev_docs)
        for runstr in dev_runs:
            if "multi" in runstr:
                cand = "multi"
            else: cand = "single"
            extracted_nl, extracted_en = extractedPerLanguage(nl_docs, en_docs,
                                                              runstr)
            if len(nl_truth) > 0:
                nl_res = performance(extracted_nl, nl_truth, beta)
                perf_nl = [nl_res['precision'], nl_res['recall'], nl_res[f_str]]
                wr.writerow([runstr] + perf_nl + ["nl", cand])
            if len(en_truth) > 0:
                en_res = performance(extracted_en, en_truth, beta)
                perf_en = [en_res['precision'], en_res['recall'], en_res[f_str]]
                wr.writerow([runstr] + perf_en + ["en", cand])

def allParamStrings(misc_strings, end=10):
    param_strings = []
    for i in range(0, end):
        conf = float(i)/10
        supp = 20*(i**2)
        for mstr in misc_strings:
            single_str = '%s_%s_c%s_s%s' % ("single", mstr, conf, supp)
            param_strings.append(single_str.replace(".", "_"))
            single_str = '%s_%s_c%s_s%s' % ("single", mstr, 0.0, supp)
            param_strings.append(single_str.replace(".", "_"))
            single_str = '%s_%s_c%s_s%s' % ("single", mstr, conf, 0)
            param_strings.append(single_str.replace(".", "_"))
            multi_str = '%s_%s_c%s_s%s' % ("multi", mstr, conf, supp)
            param_strings.append(multi_str.replace(".", "_"))
            multi_str = '%s_%s_c%s_s%s' % ("multi", mstr, 0.0, supp)
            param_strings.append(multi_str.replace(".", "_"))
            multi_str = '%s_%s_c%s_s%s' % ("multi", mstr, conf, 0)
            param_strings.append(multi_str.replace(".", "_"))
    return param_strings

def loadDevDocs():
    #read dev_truth docs from Mongo
    dev_docs_en = cpr.loadDocuments(
        {'dev_truth': {'$exists': 1}, 'origin': {'$ne': 'linkedin'},
         'language': 'en'})
    dev_docs_en += cpr.loadDocuments(
        {'dev_truth': {'$exists': 1}, 'origin': 'linkedin',
         'language': 'en'}, cpr.LinkedInProfile)
    dev_docs_nl = cpr.loadDocuments(
        {'dev_truth': {'$exists': 1}, 'language': 'nl'})

    print "EN:", [doc._id for doc in dev_docs_en]
    print "NL:", [doc._id for doc in dev_docs_nl]

    return dev_docs_en, dev_docs_nl

def csvStatementDict(profile):
    # Save a CSV table of all statements in a Profile
    header = ["Origin", "Ann_ID", "Skill", "Knowledge", "Interest"]
    with open('csv_output/%s.tab' % profile.pseudo, 'wb') as tsvfile:
        wr = csv.writer(tsvfile, delimiter="\t")
        wr.writerow(header)
        for orig, ext_inf in profile.statements.iteritems():
            for statement in ext_inf['extracted'].iteritems():
                ann_id = statement[0]
                lvl_dict = statement[1].copy()
                skill_lvl = lvl_dict['skill']
                knowl_lvl = lvl_dict['knowledge']
                inter_lvl = lvl_dict['interest']
                wr.writerow((orig, ann_id, skill_lvl, knowl_lvl, inter_lvl))
  
            
if __name__ == '__main__' :

    #judgeLinkedIn()
    #judgeCourseDescriptions()
    #judgeShareworksPortfolio()
    #judgeWebsites()

##    # Evaluate Parameter Sweeps
##    dev_docs_en, dev_docs_nl = loadDevDocs()
##    
##    new_runs = cpr.devParamSweep(dev_docs_en, "szt")
##    print "\n\n", new_runs 
##    old_runs = ["multi_szt_p4_c0_0_s0", "multi_t10_nl_c0_0_s0", "t10p4_c0_0_s0"]
##       
##    devStatements(dev_docs_en, new_runs, verbose=1)
##    sweeps = allParamStrings(["p8", "p6", "p4", "dbp", "szt"])
##
##    runs = sweeps + old_runs
##    dev_docs = dev_docs_nl + dev_docs_en
##    runLangEvalTable(dev_docs, runs)
##    csvEvalTable(dev_docs, runs)

    # Evaluate Mastery Levels
    # Load profiles and filter them for non-participants
    all_profiles = cpr.loadProfiles()
    all_profiles[:] = [pr for pr in all_profiles if (pr.signup['email'] not in
                                                     {"alex@olieman.net",
                                                      "r.jelierse@student.tudelft.nl"})]
    
