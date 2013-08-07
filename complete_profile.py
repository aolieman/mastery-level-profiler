#!/usr/bin/env python
import pymongo, os, json, scipy
import nltk.tokenize, nltk.stem
import compare, tudelft, shareworks
from math import log10, isnan
# TODO import simplejson as json, use sort_by_key=json.simple_first
from collections import defaultdict

# Load vocabulary into several convenient HashMaps (dicts)
def loadNamesFields(vocabulary):
    names_fields = {}
    for t_d in vocabulary:
        fields_dict = dict(t_d)
        for field in ('primary_industry', 'growth_rate'):
            try: del fields_dict[field]
            except KeyError: continue
        names_fields[t_d['name']] = fields_dict
    return names_fields

vocabulary = compare.readVocabulary('vocabulary_man.json')
term_ids, nl_dict, en_dict, en_summary = compare.getTermIDs(vocabulary)
names_fields = loadNamesFields(vocabulary)
del vocabulary # no need to keep this in RAM

# Set up annotation functions
def initializeParameters(cand, misc, con, sup):
    global candidate_param, confidence, support
    global parameter_str, title_ann, title_resp
    global header_ann, header_resp, text_ann, text_resp
    candidate_param = cand # 'single' for /annotate, 'multi' for /candidates
    confidence = con
    support = sup
    misc_params = misc
    parameter_str = '_%s_%s_c%s_s%s' % (candidate_param, misc_params, confidence, support)
    parameter_str = str(parameter_str).replace('.', '_')
    title_ann = 'title_ann' + parameter_str
    title_resp = 'title_resp' + parameter_str
    header_ann = 'h_ann' + parameter_str
    header_resp = 'h_resp' + parameter_str
    text_ann = 'txt_ann' + parameter_str
    text_resp = 'txt_resp' + parameter_str
    print "Parameters set to:", parameter_str[1:]
    return parameter_str[1:]

# Initialize parameters to high-recall settings
initializeParameters("multi", "p8", 0.0, 0)

# establish a connection to the MongoDB
db = pymongo.Connection('localhost', 27017)['mastery_level_profiler']

# set of ann_ids that are too general and are thus ignored
# "Prostitution" was added because it can be offensive
ignored_ann_ids = {"Academic_term", "Author", "Code", "Conducting", "Consideration", "Course_(education)",
                   "College", "Diploma", "Faculty_(division)", "Further_education", "Hobby", "Home",
                   "Graduate_school", "Graduation", "Human", "Job_(role)", "Life", "Laborer", "Privately_held_company",
                   "Printing", "Professor", "Safe", "School", "Prostitution",
                   "Secondary_education", "Solution", "Student", "Supervisor",
                   "Theory", "Tutorial", "University", "Van", "Vocational_education"}
# set of ann_ids that occur in course descriptions, but don't say much about the course
ignored_tudelft = {"Blackboard_Learning_System", "Book", "Bookselling", "Education", "Blackboard_Inc~",
                   "Curriculum", "Deliverable", "Demand_(economics)", "Epistemology", "Feedback",
                   "Higher_education", "Lecture", "Literature", "Material",
                   "Master_class", "Mass", "Print_on_demand", "Reference", "Summary",
                   "Email", "Homework", "Training", "Symposium", "Engineer"}
# set of ann_ids that occur in portfolios/websites, but don't say much about the project/student
ignored_shw_web = {"Deliverable", "Education", "Female", "Graduation",
                   "Image", "Male", "Output", "Project", "Woman"}

# Translation dict (ann_id->ann_id) for domain-specific abbreviations
ide_abbr = {"Integrated_development_environment": u'Product_design',
            "Internally_displaced_person": u'New_product_development',
            "Very_Important_Person": u'Vision_in_Product_Design'}

class Profile(object):
    def __init__(self, **entries):
        self.__dict__.update(entries)

    def toMongo(self):
        return db.profile.save(self.__dict__)

    def addStatements(self, param_str_en, param_str_nl, new_statements=True):
        # Initialize empty StatementDicts
        li_ext, tu_ext = StatementDict(), StatementDict()
        sw_ext, ws_ext = StatementDict(), StatementDict()
        # Get LinkedIn StatementDict, if available
        try:
            li_doc = LinkedInProfile(**db.document.find_one({"_id": self.linkedin}))
        except AttributeError:
            print "!! %s has not connected LinkedIn" % self.signup['email']
        else:
            try:
                if new_statements: li_doc.makeStatements(param_str_en)
                li_ext = StatementDict(getattr(li_doc, param_str_en)['extracted'])
            except AttributeError:
                print "!! %s has no statements for %s" % (li_doc.title, param_str)
        # Get statements for each course description; weight by grade
        for course_doc, weight in self.iterTUDocs():
            if course_doc.language == "en": param_str = param_str_en
            elif course_doc.language == "nl": param_str = param_str_nl
            else: raise Exception("Unknown language: %s" % course_doc.language)
            try:
                if new_statements: course_doc.makeStatements(param_str)
                doc_ext = StatementDict(getattr(course_doc, param_str)['extracted'])
                doc_ext.weightStmts(weight)
                tu_ext.update(doc_ext)
            except AttributeError:
                print "!! %s has no statements for %s" % (course_doc.title, param_str)
        # Get statements for each portfolio document
        for sw_doc in self.iterPortfolioDocs():
            if sw_doc.language == "en": param_str = param_str_en
            elif sw_doc.language == "nl": param_str = param_str_nl
            else: raise Exception("Unknown language: %s" % sw_doc.language)
            try:
                if new_statements: sw_doc.makeStatements(param_str)
                doc_ext = StatementDict(getattr(sw_doc, param_str)['extracted'])
                sw_ext.update(doc_ext)
            except AttributeError:
                print "!! %s has no statements for %s" % (sw_doc._id, param_str)
        # Get statements for each website document
        for webpage in self.iterWebsiteDocs():
            try:
                if new_statements: webpage.makeStatements(param_str)
                doc_ext = StatementDict(getattr(webpage, param_str)['extracted'])
                ws_ext.update(doc_ext)
            except AttributeError:
                print "!! %s has no statements for %s" % (webpage.title, param_str)
           
        self.statements = {'linkedin': {'extracted': li_ext, 'inferred': {}},
                           'tudelft': {'extracted': tu_ext, 'inferred': {}},
                           'shareworks': {'extracted': sw_ext, 'inferred': {}},
                           'website': {'extracted': ws_ext, 'inferred': {}}}

        # Save profile to Mongo
        self.toMongo()

    def scaleStatements(self, max_ski_dict):
        all_ext = StatementDict()
        for origin in self.statements:
            extracted = self.statements[origin]['extracted']
            # Scale StatementDicts and assign to attribute
            extracted.scaleDomain(max_ski_dict[origin])
            # Use the sum of statements (scaled per origin) as all_dict
            all_ext.update(extracted)
            
        # Add 'ALL' as origin
        self.statements['ALL'] = {'extracted': all_ext, 'inferred': {}}
        # Save profile to Mongo
        self.toMongo()

    def transformStatements(self, master_lvls_dict):
        # Transform scaled values to percentiles
        for origin in self.statements:
            extracted = self.statements[origin]['extracted']
            extracted.toPercentiles(master_lvls_dict[origin])

        # Save profile to Mongo
        self.toMongo()

    def uniqueTopics(self):
        # Find sets of topics that are unique to origin=tudelft/shareworks
        li_set = set(self.statements['linkedin']['extracted'])
        tu_set = set(self.statements['tudelft']['extracted'])
        sw_set = set(self.statements['shareworks']['extracted'])
        ws_set = set(self.statements['website']['extracted'])
        tu_unique = tu_set.difference(li_set, sw_set, ws_set)
        sw_unique = sw_set.difference(tu_set, li_set, ws_set)
        # Randomly sample half of each set, return the union
        import random
        tu_sample = set(random.sample(tu_unique, len(tu_unique)/2))
        sw_sample = set(random.sample(sw_unique, len(sw_unique)/2))
        return tu_sample.union(sw_sample)

    def statementsToJSON(self):
        # Serialize 'ALL' statements to JSON file
        all_stmts = self.statements['ALL'].copy() #still affects self.statements, use dict()?
        # Get half of unique topics, to mark as "don't judge lvls"
        no_judge_lvl = self.uniqueTopics()
        # Extracted statements
        ext_dict = StatementDict(map(lambda (k,v): (k, roundLvls(v)),
                       all_stmts['extracted'].iteritems()))
        for ann_id, lvl_dict in ext_dict.iteritems():
            try:
                lvl_dict['name'] = en_dict[ann_id.replace("~", ".")]
                lvl_dict['summary'] = en_summary[ann_id.replace("~", ".")]
                if not lvl_dict['summary']:
                    lvl_dict['summary'] = "Sorry, no description is available."
            except KeyError:
                lvl_dict['name'] = ann_id.replace("~", ".")
                lvl_dict['summary'] = "Sorry, no description is available."
            finally:
                lvl_dict['judge_lvl'] = True
                if ann_id in no_judge_lvl:
                    lvl_dict['judge_lvl'] = False
                    print "Don't judge level: %s" % ann_id
        # Inferred statements
        for key in all_stmts['inferred']:
            all_stmts['inferred'][key] = all_stmts['inferred'][key][:10]
        inf_dict = all_stmts['inferred']
        # Write to file
        secret = str(self._id)[-5:]
        to_file = {'pseudo': self.pseudo,
                   'extracted': ext_dict, 'inferred': inf_dict}
        with open("review/json/%s.json" % self.pseudo, "wb") as ofile:
            json.dump(to_file, ofile, indent=4, sort_keys=True)
        return (self.pseudo, secret)

    def getDbpediaInferences(self, inf_topics_dbpedia, fields_dbp):
        for origin in self.statements:
            ext_topics = set(self.statements[origin]['extracted'].keys())
            super_flowdict = defaultdict(float)
            for ext_id in ext_topics:
                ext_id = ext_id.replace("~", ".")
                try:
                    for inf_id, flowct in inf_topics_dbpedia[ext_id].iteritems():
                        if inf_id in ext_topics: continue # TODO: check Mongo escape
                        super_flowdict[inf_id] += flowct
                except KeyError:
                    print "No DBp inferences for %s" % ext_id
            top_flow = sorted(super_flowdict.items(), key=lambda tup: tup[1],
                              reverse=True)[:100]
            # Fill in-vocab and not-in-vocab lists with top-10
            dbp_infs, dbp_infs_niv = [], []
            ignore_topics = {'List_of_style_guides', 'Aaron_Marcus',
                             'List_of_schools_offering_interaction_design_programs'}
            for inf_id, flowct in top_flow:
                if inf_id in ignore_topics: continue
                topic_dict = {'enid': inf_id, 'flow': flowct, 'correct': True}
                if inf_id in en_dict:
                    topic_dict['name'] = en_dict[inf_id]
                    topic_dict['summary'] = en_summary[inf_id]
                    dbp_infs.append(topic_dict)
                else:
                    try:
                        topic_dict['name'] = fields_dbp[inf_id]['label']
                        topic_dict['summary'] = fields_dbp[inf_id]['summary']
                        dbp_infs_niv.append(topic_dict)
                    except KeyError:
                        print "No DBp fields found for %s" % inf_id
                if len(dbp_infs) >= 10 and len(dbp_infs_niv) >= 10: break
            # Save in self.statements[origin]
            self.statements[origin]['inferred']['dbp'] = dbp_infs
            self.statements[origin]['inferred']['dbp_niv'] = dbp_infs_niv
            
        # Save in MongoDB and return inferred topics for ALL
        self.toMongo()
        inf_all = self.statements['ALL']['inferred']
        return inf_all['dbp'], inf_all['dbp_niv']          
        

    def getLinkedinInferences(self, names_fields):
        for origin in self.statements:
            ext_topics = set(self.statements[origin]['extracted'].keys())
            count_rel = defaultdict(int)
            for ext_id in ext_topics:
                ext_id = ext_id.replace("~", ".")
                try:
                    ext_name = en_dict[ext_id]
                except KeyError: print "\n!! %s not a recognized ann_id\n" % ext_id
                rels = []
                if 'related_skills' in names_fields[ext_name]:
                    rels = names_fields[ext_name]['related_skills']
                if 'skill_links' in names_fields[ext_name]:
                    rels += [sl[14:] for sl in names_fields[ext_name]['skill_links'] if sl]
                for rel in rels:
                    inf_name = rel.replace("_", " ")
                    count_rel[inf_name] += 1
                if len(rels) == 0: print "No LI related topics for %s" % ext_id
            top_flow = sorted(count_rel.items(), key=lambda tup: tup[1],
                              reverse=True)
            # Fill in-vocab (URI) and not-in-vocab (no URI) lists with top-10
            from get_vocabulary import manually_corrected # names not changed in rel_skills
            li_infs, li_infs_niv = [], []
            for inf_name, count in top_flow:
                if inf_name in manually_corrected:
                    inf_name = manually_corrected[inf_name][0]
                try:
                    fields = names_fields[inf_name]
                except KeyError:
                    print "\n!! %s not a recognized skill name\n" % inf_name
                    continue
                topic_dict = {'name': inf_name, 'count': count, 'correct': True}
                topic_dict['summary'] = "Sorry, no description is available."
                if 'summary' in fields and fields['summary']:
                    topic_dict['summary'] = fields['summary']
                if 'more_wiki' in fields:
                    inf_id = fields['more_wiki'].split("wiki/")[1]
                    topic_dict['enid'] = inf_id
                    if inf_id in ext_topics: continue
                    li_infs.append(topic_dict)
                else: li_infs_niv.append(topic_dict)
                if len(li_infs) >= 10 and len(li_infs_niv) >= 10: break
            # Save in self.statements[origin]
            self.statements[origin]['inferred']['li'] = li_infs
            self.statements[origin]['inferred']['li_niv'] = li_infs_niv

        # Save in MongoDB and return inferred topics for ALL
        self.toMongo()
        inf_all = self.statements['ALL']['inferred']
        return inf_all['li'], inf_all['li_niv']

    def updateLinkedInDoc(self):
        if hasattr(self, 'linkedin') and db.document.find_one({"_id": self.linkedin}):
            doc_from_mongo = db.document.find_one({"_id": self.linkedin})
            doc_object = LinkedInProfile(**doc_from_mongo)
            new_oid = linkedinToDoc(self.signup['linkedin'], doc_object)
            if new_oid != self.linkedin:
                raise UnequalIDsException(new_oid +" is not "+ self.linkedin)
        elif 'linkedin' in self.signup:
            self.linkedin = linkedinToDoc(self.signup['linkedin'])
            self.toMongo() # save new doc_id
        else: print "!! %s has not connected LinkedIn" % self.signup['email']

    def annotateDocs(self):
        ## Depends on global parameters for annotation checks
        print "\n\n", self.signup['email']
        # Annotate LinkedIn profile
        if hasattr(self, 'linkedin'):
            li_profile = LinkedInProfile(**db.document.find_one({"_id": self.linkedin}))
            # check if the document has been annotated
            if text_ann not in li_profile.content[0]:
                li_profile.annotate()
            else: print li_profile.title, "has already been annotated"
        else: print "!! "+self.signup['email']+" has not connected LinkedIn"
        # Annotate course documents
        for course_doc, weight in self.iterTUDocs():
            # check if the document has been annotated
            if text_ann not in course_doc.content[0]:
                course_doc.annotate(title=True)
            else: print course_doc.title, "has already been annotated"
        # Annotate webpage documents
        for webpage in self.iterWebsiteDocs():
            # check if the document has been annotated
            if text_ann not in page.content[0]:
                page.annotate(title=True)
            else: print page.title, "has already been annotated"
        # Annotate project portfolio
        for sw_doc in self.iterPortfolioDocs():
            # check if the document has been annotated
            if text_ann not in doc.content[0]:
                doc.annotate()
            else: print doc._id, "has already been annotated"

        print "Annotations for "+self.signup['email']+" are done"

    def iterTUDocs(self):
        # Generator function that yields course documents from Mongo
        if self.tudelft == None:
            print "!! %s has not connected TU Delft" % (self.signup['email'], )
            raise StopIteration
        else:
            for course in self.tudelft:
                if course['voldoende'] == "false": continue
                grade_str = course['resultaat'].replace(',', '.')
                if grade_str == "V": grade_str = "7.0"
                weight = ((2 + float(course['ectspunten'])/2)
                          /(11 - float(grade_str)))
                course_doc = tudelft.courseDoc(course['cursusid'], course['collegejaar'])
                if course_doc == None: continue
                yield course_doc, weight

    def iterWebsiteDocs(self):
        # Generator function that yields webpage documents from Mongo
        if hasattr(self, 'website'):
            for webpage in self.website:
                yield Document(**db.document.find_one({"_id": webpage}))
        else:
            print "!! %s doesn't have a website" % (self.signup['email'], )
            raise StopIteration

    def iterPortfolioDocs(self):
        # Generator function that yields portfolio documents from Mongo
        if hasattr(self, 'portfolio'):
            for sw_doc in self.portfolio:
                yield Document(**db.document.find_one({"_id": sw_doc}))
        else:
            print "!! %s doesn't have a portfolio" % (self.signup['email'], )
            raise StopIteration

class Document(object):
    def __init__(self, **entries):
        self.language = "en"
        self.content = []
        self.__dict__.update(entries)

    def toMongo(self):
        return db.document.save(self.__dict__)

    def annotate(self, header=False, text=True, title=False, mongo=True):
        if hasattr(self, "title"):
            print "\nAnnotations for " + self.title
        else: print "\nAnnotations for", self._id
        if title:
            sp_tuple = compare.throughSpotlight(self.title, candidate_param,
                                                confidence, support, 'en')
            if sp_tuple == None:
                pass
            else:
                if candidate_param == "single":
                    setattr(self, title_ann, sorted(list(set(sp_tuple[0]).intersection(term_ids))))
                elif candidate_param == "multi":
                    title_ann_ids = unwrapCandidates(sp_tuple[0])
                    setattr(self, title_ann, title_ann_ids)
                else: raise Exception("Incorrect candidate_param provided")
                print getattr(self, title_ann)
                setattr(self, title_resp, sp_tuple[1])
        for section in self.content:
            if header:
                if len(section['header'].strip()) > 3:
                    sp_tuple = compare.throughSpotlight(section['header'], candidate_param,
                                                        confidence, support, self.language)
                    if sp_tuple == None:
                        pass
                    else:
                        if candidate_param == "single":
                            section[header_ann] = sorted(list(set(sp_tuple[0]).intersection(term_ids)))
                        elif candidate_param == "multi":
                            section[header_ann] = unwrapCandidates(sp_tuple[0])
                        else: raise Exception("Incorrect candidate_param provided")
                        if self.language == 'nl': # translate Dutch IDs
                            section[text_ann] = translateDutchIDs(section[text_ann])
                        print section[header_ann]
                        section[header_resp] = sp_tuple[1]
            if text:
                if len(section['text'].strip()) > 3: #quickfix for empty strings
                    sp_tuple = compare.throughSpotlight(section['text'], candidate_param,
                                                        confidence, support, self.language)
                    if sp_tuple == None:
                        continue
                    else:
                        if candidate_param == "single":
                            section[text_ann] = sorted(list(set(sp_tuple[0]).intersection(term_ids)))
                        elif candidate_param == "multi":
                            section[text_ann] = unwrapCandidates(sp_tuple[0])
                        else: raise Exception("Incorrect candidate_param provided")
                        if self.language == 'nl': # translate Dutch IDs
                            section[text_ann] = translateDutchIDs(section[text_ann])
                        print section[text_ann]
                        section[text_resp] = sp_tuple[1]
        # if the mongo boolean is set, save to MongoDB
        if mongo: self.toMongo()

    def makeStatements(self, param_str, del_resp=False, verbose=0):
        extracted = StatementDict()
        # TODO: Title annotations
        ## Add annotations for all sections to all_ann_ids
        for s in self.content:
            all_ann_ids = set()
            for key in s.keys():
                if key[:7] == "txt_ann" or key[:5] == "h_ann":
                    if param_str == "dev_truth":
                        all_ann_ids.update(s[key])
                    elif param_str in key:
                        try: all_ann_ids.update(s[key])
                        except TypeError, e:
                            print key, e
                        if del_resp: # mainly for use with devParamSweep()
                            try:
                                del s[key.replace("ann", "resp")] # del response
                            except KeyError:
                                pass
            all_ann_ids.difference_update(ignored_ann_ids)
            ## Mongo escape and translate abbreviations
            for ann_id in all_ann_ids:
                if "." in ann_id: # replacement hack for forbidden Mongo char
                    mongo_escaped = ann_id.replace(".", "~")
                    all_ann_ids.remove(ann_id)
                    all_ann_ids.add(mongo_escaped)
                    if verbose > 0:
                        print "%s was replaced with %s" % (ann_id, mongo_escaped)
                if ann_id in ide_abbr: # Domain-specific abbreviations
                    all_ann_ids.remove(ann_id)
                    all_ann_ids.add(ide_abbr[ann_id])
            ## Look for qualifying terms and compute fractions
            know_terms, skill_terms = qualifyingTerms(s['text'], self.language)
            if len(know_terms) == len(skill_terms): fK = 0.5
            elif len(know_terms) > 0:
                fK = len(know_terms) / float(len(know_terms) + len(skill_terms))
            else: fK = 0.0
            fS = 1.0 - fK
            if fS > 0.5: fK += fS/3 #skill implies some knowledge
            if verbose > 0: print "Knowledge", fK, know_terms
            if verbose > 0: print "Skill", fS, skill_terms
            ## Process statements per origin
            if self.origin == 'tudelft':
                # TODO: incorporate course grades for lvl
                all_ann_ids.difference_update(ignored_tudelft)
                for ann_id in all_ann_ids:
                    extracted.add(statement(ann_id, fS*4, fK*4, 0.0))
            elif self.origin == 'shareworks':
                # TODO: incorporate doc_type for lvl?
                all_ann_ids.difference_update(ignored_shw_web)
                for ann_id in all_ann_ids:
                    extracted.add(statement(ann_id, fS*2, fK*2, 0.5))
            elif self.origin == 'website':
                # TODO: incorporate doc_type for lvl?
                all_ann_ids.difference_update(ignored_shw_web)
                for ann_id in all_ann_ids:
                    extracted.add(statement(ann_id, fS*4, fK*4, 2.0))

        # Statements are saved to a param_str attribute
        if len(extracted) > 0:
            setattr(self, param_str, {'extracted': extracted})
            try: self.toMongo()
            except pymongo.errors.InvalidDocument:
                print "!!Document too large, deleting responses"
                for s in self.content:
                    for key in s.keys():
                        if "resp" in key:
                            del s[key]
                            print key, "deleted"

class UnequalIDsException(pymongo.errors.InvalidId):
    pass

def qualifyingTerms(string, lang_str):
    know_terms, skill_terms = set(), set()
    if lang_str == "en":
        stemmer = nltk.stem.snowball.EnglishStemmer(ignore_stopwords=True)
        know_stems = {u'analysi', u'analyz', u'debat', u'discuss', u'explain',
                      u'know', u'knowledg', u'literatur', u'method',
                      u'methodolog', u'theoret', u'theori', u'understand'}
        skill_stems = {u'abil', u'appli', u'applic', u'compet', u'develop',
                       u'execut', u'practic', u'project', u'skill', u'train'}
    else:
        stemmer = nltk.stem.snowball.DutchStemmer(ignore_stopwords=True)
        know_stems = {u'analys', u'analyser', u'bediscussier', u'begrijp',
                      u'begrijpt', u'begrip', u'kenn', u'kennis', u'kent',
                      u'literatur', u'methodes', u'methodologie',
                      u'theoretisch', u'theorie', u'uitleg', u'uitlegg', u'wet'}
        skill_stems = {u'competentie', u'competenties', u'getraind', 'kan',
                       'kunnen', u'ontwikkel', u'ontwikkeld', u'opdracht',
                       u'practica', u'practicum', u'project', u'toegepast',
                       u'toepass', u'train', u'training', u'uitvoer', u'vaardig'}
    tokzd = nltk.tokenize.wordpunct_tokenize(string)
    for tok in tokzd:
        stem = stemmer.stem(tok)
        if stem in know_stems:
            know_terms.add(stem) # or add token instead?
        elif stem in skill_stems:
            skill_terms.add(stem)
    return know_terms, skill_terms

class LinkedInProfile(Document):
    """
    Makes statements from underlying annotations.
    For now only extracted statements.
    """
    def makeStatements(self, param_str, del_resp=False):
        extracted = StatementDict()
        try:
            for name in self.skills:
                try:
                    fields = names_fields[name] # Need to search by name
                    ann_id = fields['more_wiki'].split("wiki/")[1]
                    extracted.add(statement(ann_id, 3.0, 3.0, 3.0))
                except KeyError: print "No known URI for skill '%s'" % name 
        except AttributeError:
            print "No LI Skills in %s" % self.title
        for s in self.content:
            all_ann_ids = set()
            for key in s.keys():
                if key[:7] == "txt_ann" or key[:5] == "h_ann":
                    if param_str == "dev_truth":
                        all_ann_ids.update(s[key])
                    elif param_str in key:
                        all_ann_ids.update(s[key])
                        if del_resp: # mainly for use with devParamSweep()
                            try:
                                del s[key.replace("ann", "resp")] # del response
                            except KeyError:
                                pass
            all_ann_ids.difference_update(ignored_ann_ids)
            for ann_id in all_ann_ids:
                if "." in ann_id: # replacement hack for forbidden Mongo char
                    mongo_escaped = ann_id.replace(".", "~")
                    all_ann_ids.remove(ann_id)
                    all_ann_ids.add(mongo_escaped)
                    print "%s was replaced with %s" % (ann_id, mongo_escaped)
                if ann_id in ide_abbr: # Domain-specific abbreviations
                    all_ann_ids.remove(ann_id)
                    all_ann_ids.add(ide_abbr[ann_id])
            if s['header'] in {"Headline", "Summary", "Specialties"}:
                for ann_id in all_ann_ids:
                    extracted.add(statement(ann_id, 2.0, 1.0, 1.0))
            elif s['header'] in {"Honors", "Certifications"}:
                for ann_id in all_ann_ids:
                    extracted.add(statement(ann_id, 2.0, 1.0, 0.0))
            elif s['header'] == "Interests":
                for ann_id in all_ann_ids:
                    extracted.add(statement(ann_id, 0.0, 1.0, 3.0))
            elif s['header'] == "Volunteer Experience":
                for ann_id in all_ann_ids:
                    extracted.add(statement(ann_id, 1.0, 1.0, 2.0))
            elif s['header'] in {"Volunteer Causes", "Volunteer Support"}:
                for ann_id in all_ann_ids:
                    extracted.add(statement(ann_id, 0.0, 1.0, 2.0))
            elif s['header'] in {"Education", "Courses"}:
                for ann_id in all_ann_ids:
                    extracted.add(statement(ann_id, 1.0, 2.0, 0.0))
            elif s['header'] == "Position":
                for ann_id in all_ann_ids:
                    extracted.add(statement(ann_id, 2.0, 1.0, 0.0))
            elif s['header'] == "Recommendation":
                for ann_id in all_ann_ids:
                    extracted.add(statement(ann_id, 2.0, 1.0, 1.0))
            else:
                print "! Header %s not recognized !" % s['header']

        # Statements are saved to a param_str attribute
        if len(extracted) > 0:
            setattr(self, param_str, {'extracted': extracted})
            try: self.toMongo()
            except pymongo.errors.InvalidDocument:
                print "!!Document too large, deleting responses"
                for s in self.content:
                    for key in s.keys():
                        if "resp" in key:
                            del s[key]
                            print key, "deleted"

def statement(ann_id, skill=0, knowledge=0, interest=0):
    lvl_dict = {'skill': float(skill),
                'knowledge': float(knowledge),
                'interest': float(interest)}
    return (ann_id, lvl_dict)

def roundLvls(lvl_dict):
    # Round values to nearest integer
    for m_type, lvl in lvl_dict.iteritems():
        lvl_dict[m_type] = int(round(lvl))
    return lvl_dict

def prfloats(lvl_dict):
    # Pretty printing for floats in lvl_dict
    fmt_dict = {}
    fmt_dict['skill'] = "{0:0.2f}".format(lvl_dict['skill'])
    fmt_dict['knowledge'] = "{0:0.2f}".format(lvl_dict['knowledge'])
    fmt_dict['interest'] = "{0:0.2f}".format(lvl_dict['interest'])
    return fmt_dict

class StatementDict(dict):
    # Container for single S,K,I values per ann_id
    def __str__(self):
        str_out = str()
        value_sort = sorted(self.iteritems(), reverse=True,
                            key=lambda t: sum(t[1].values()))
        for ann_id, lvl_dict in value_sort:
            fmt_dict = prfloats(lvl_dict)
            str_out += "\n"+(repr(ann_id)+": ").ljust(20)+str(fmt_dict)
        return str_out
        
    def add(self, statement):
        ann_id = statement[0]
        lvl_dict = statement[1].copy()
        if ann_id in self:
            self[ann_id]['skill'] += lvl_dict['skill']
            self[ann_id]['knowledge'] += lvl_dict['knowledge']
            self[ann_id]['interest'] += lvl_dict['interest']
        else:
            self[ann_id] = lvl_dict

    def update(self, statement_dict):
        for statement in statement_dict.iteritems():
            self.add(statement)

    def getMaxSKI(self):
        if len(self) == 0: return 0, 0, 0
        # Compute max skill, knowledge, interest
        skill_max = max(self.itervalues(), key=lambda ld: ld['skill'])
        knowl_max = max(self.itervalues(), key=lambda ld: ld['knowledge'])
        inter_max = max(self.itervalues(), key=lambda ld: ld['interest'])
        return skill_max['skill'], knowl_max['knowledge'], inter_max['interest']

    def scaleDomain(self, max_ski):
        # Scale min and max values for each statement (overwrite)
        # Log transformation and linear scale 0-100
        for lvls in self.itervalues():
            lvls['skill'] = 100 * log10(lvls['skill']+1) / log10(max_ski[0]+1)
            lvls['knowledge'] = 100 * log10(lvls['knowledge']+1) / log10(max_ski[1]+1)
            lvls['interest'] = 100 * log10(lvls['interest']+1) / log10(max_ski[2]+1)

    def toPercentiles(self, lvls_ld):
        # Transform values for each statement to percentiles (overwrite)
        val_to_perc = scipy.stats.percentileofscore
        for ann_id, lvl_dict in self.iteritems():
            if lvl_dict['skill'] > 0:
                lvl_dict['skill'] = val_to_perc(lvls_ld[ann_id]['skill'],
                                                lvl_dict['skill'], "mean")
            if lvl_dict['knowledge'] > 0:
                lvl_dict['knowledge'] = val_to_perc(lvls_ld[ann_id]['knowledge'],
                                                lvl_dict['knowledge'], "mean")
            if lvl_dict['interest'] > 0:
                lvl_dict['interest'] = val_to_perc(lvls_ld[ann_id]['interest'],
                                                lvl_dict['interest'], "rank")        

    def weightStmts(self, weight, verbose=0):
        for ann_id in self:
            if verbose: print("{0:0.2f} x".format(weight),
                              ann_id, prfloats(self[ann_id]))
            self[ann_id]['skill'] *= weight
            self[ann_id]['knowledge'] *= weight
            self[ann_id]['interest'] *= weight
            if verbose: print "Done :", ann_id, prfloats(self[ann_id])


def maxPerOrigin(all_profiles):
    # TODO: perhaps refactor to use lvlsPerOrigin
    li_max_tuples, tu_max_tuples = [], [(0,0,1)] #hack for max(tu_int) = 0
    sw_max_tuples, ws_max_tuples = [], []
    # Get max S,K,I per profile per origin
    for pr in all_profiles:
        li_max_tuples.append(StatementDict(pr.statements['linkedin']
                                           ['extracted']).getMaxSKI())
        tu_max_tuples.append(StatementDict(pr.statements['tudelft']
                                           ['extracted']).getMaxSKI())
        sw_max_tuples.append(StatementDict(pr.statements['shareworks']
                                           ['extracted']).getMaxSKI())
        ws_max_tuples.append(StatementDict(pr.statements['website']
                                           ['extracted']).getMaxSKI())

    # Get the maximums across all profiles
    li_max = (max(li_max_tuples, key=lambda t: t[0])[0],
              max(li_max_tuples, key=lambda t: t[1])[1],
              max(li_max_tuples, key=lambda t: t[2])[2])
    tu_max = (max(tu_max_tuples, key=lambda t: t[0])[0],
              max(tu_max_tuples, key=lambda t: t[1])[1],
              max(tu_max_tuples, key=lambda t: t[2])[2])
    sw_max = (max(sw_max_tuples, key=lambda t: t[0])[0],
              max(sw_max_tuples, key=lambda t: t[1])[1],
              max(sw_max_tuples, key=lambda t: t[2])[2])
    ws_max = (max(ws_max_tuples, key=lambda t: t[0])[0],
              max(ws_max_tuples, key=lambda t: t[1])[1],
              max(ws_max_tuples, key=lambda t: t[2])[2])
    # Return max S,K,I per origin in dict
    max_ski_dict = {'linkedin': li_max, 'tudelft': tu_max,
                'shareworks': sw_max, 'website': ws_max}
    return max_ski_dict

class LvlsListDict(dict):
    # Container for list S,K,I values per ann_id
    def __str__(self):
        str_out = str()
        value_sort = sorted(self.iteritems(), reverse=True,
                            key=lambda t: sum([len(l) for l in t[1].values()]))
        for ann_id, lvls_dict in value_sort:
            str_out += "\n\n"+(repr(ann_id)+": ").ljust(20)+str(lvls_dict)
        return str_out
    
    def append(self, statement):
        ann_id = statement[0]
        lvl_dict = statement[1].copy()
        if ann_id not in self:
            self[ann_id] = {'skill': [], 'knowledge': [], 'interest': []}
        for mastery_type, lvl in lvl_dict.iteritems():
            # lvl of 0.0 means: no S/K/I could be implied, so don't count
            if lvl > 0:
                self[ann_id][mastery_type].append(lvl)                

    def updAppend(self, statement_dict):
        for statement in statement_dict.iteritems():
            self.append(statement)

    def smoothLists(self, multiplier):
        # Insert evenly spaced values [0.0 - multiplier*max(lvls_list)]
        for lvls_dict in self.itervalues():
            for lvls_list in lvls_dict.itervalues():
                if len(lvls_list) > 0:
                    max_lvl = multiplier*max(lvls_list)
                    insert_lvls = [n_lvl * max_lvl / len(lvls_list)
                                   for n_lvl in xrange(len(lvls_list)+1)]
                    lvls_list[:] = sorted(insert_lvls + lvls_list)
        return self
                    

def lvlsPerOrigin(all_profiles):
    li_lvls_dict, tu_lvls_dict = LvlsListDict(), LvlsListDict()
    sw_lvls_dict, ws_lvls_dict = LvlsListDict(), LvlsListDict()
    all_lvls_dict = LvlsListDict()
    # Append the S,K,I values for each ann_id to corresponding lvls_dict
    for pr in all_profiles:
        li_lvls_dict.updAppend(pr.statements['linkedin']['extracted'])
        tu_lvls_dict.updAppend(pr.statements['tudelft']['extracted'])
        sw_lvls_dict.updAppend(pr.statements['shareworks']['extracted'])
        ws_lvls_dict.updAppend(pr.statements['website']['extracted'])
        all_lvls_dict.updAppend(pr.statements['ALL']['extracted'])
    multiplier = 1.5
    return {'linkedin': li_lvls_dict.smoothLists(multiplier),
            'tudelft': tu_lvls_dict.smoothLists(multiplier),
            'shareworks': sw_lvls_dict.smoothLists(multiplier),
            'website': ws_lvls_dict.smoothLists(multiplier),
            'ALL': all_lvls_dict.smoothLists(multiplier)}

"""
Takes candidate lists (as provided by compare.throughSpotlight)
and adds the top candidate that is in the term vocabulary
to the output list (if it is not in the output list yet).
"""
def unwrapCandidates(annotation_ids):
    selected_candidates = []
    for candidates in annotation_ids:
        for c in candidates:
            if c not in selected_candidates and c in term_ids:
                selected_candidates.append(c)
                break
    return sorted(selected_candidates)

def translateDutchIDs(ann_ids):
    for i in xrange(len(ann_ids)):
        try:
            ann_ids[i] = nl_dict[ann_ids[i]][0]
        except KeyError, e:
            # Dutch term is not in the vocabulary, but the English homolog is.
            print e, "is not in the Dutch vocabulary"
    return sorted(ann_ids)

def readSignups(signup_dir):
    # this function assumes the indir contains files only
    filelist = os.listdir(signup_dir)
    for f in filelist:
        signup_file = open(os.path.join(signup_dir, f), "rb")
        signup_dict = json.load(signup_file)
        signup = {'email': signup_dict['email']}
        # if email in a mongo profile, continue with next file
        profile_in_mongo = db.profile.find_one({"signup.email": signup_dict['email']})
        if profile_in_mongo:
            print signup_dict['email'], "was found in MongoDB (-> skipping)"
            continue
        
        tudelft = None
        linkedin = None
        if 'tudelft.data' in signup_dict:
            tudelft = signup_dict['tudelft.data']['studieresultaatLijst']['studieresultaat']
            signup['tudelft'] = tudelft
        if 'linkedin.id' in signup_dict:
            linkedin_kvs = [(key[9:], val) for key, val in signup_dict.items() if key[:9] == 'linkedin.']
            linkedin = {}
            for kv in linkedin_kvs:
                linkedin[kv[0]] = kv[1]
            signup['linkedin'] = linkedin
        if 'website' in signup_dict:
            signup['website'] = signup_dict['website']
        signup_file.close()
        # make object, make linkedin doc, and insert to mongo
        new_profile = Profile(signup=signup, tudelft=tudelft)
        new_profile.updateLinkedInDoc()
        print new_profile.toMongo()

def loadProfiles(): #from mongo
    result = db.profile.find()
    profiles = [Profile(**res) for res in result]
    return profiles

def loadDocuments(filter_dict=None, into_class=Document): #from mongo
    if filter_dict != None:
        result = db.document.find(filter_dict)
    else: result = db.profile.find()
    documents = [into_class(**res) for res in result]
    return documents

def linkedinToDoc(linkedin_dict, existing_doc=None):
    # remove irrelevant keys from dict
    linkedin_dict.pop('completion', None)
    linkedin_dict.pop('token', None)
    linkedin_dict.pop('id', None)

    # if this profile is new, make a new instance; else, edit it
    if existing_doc == None:
        profile_doc = LinkedInProfile(doctype="li_profile", origin="linkedin", skills=[])
    else:
        profile_doc = existing_doc
        profile_doc.old_content = profile_doc.content[:] #shallow copy
        profile_doc.content = []

    # set the profile attributes from the provided dict
    profile_doc.title = linkedin_dict['name'] + "'s LinkedIn profile"
    if 'skills' in linkedin_dict:
        profile_doc.skills = [it['skill']['name'] for it in linkedin_dict['skills']['values']]
    if 'languages' in linkedin_dict:
        profile_doc.skills += [it['language']['name'] for it in linkedin_dict['languages']['values']]
    if 'interests' in linkedin_dict:
        profile_doc.content.append({'header': 'Interests', 'text': linkedin_dict['interests']})
    if 'headline' in linkedin_dict:
        profile_doc.content.append({'header': 'Headline', 'text': linkedin_dict['headline']})
    if 'specialties' in linkedin_dict:
        profile_doc.content.append({'header': 'Specialties', 'text': linkedin_dict['specialties']})
    if 'summary' in linkedin_dict:
        profile_doc.content.append({'header': 'Summary', 'text': linkedin_dict['summary']})
    if 'honors' in linkedin_dict:
        profile_doc.content.append({'header': 'Honors', 'text': linkedin_dict['honors']})
    if linkedin_dict['positions']['_total'] > 0:
        for position in linkedin_dict['positions']['values']:
            position_text = position['title']
            position_text += "\n" + position['company']['name'] + " / " + position['company']['industry']
            if 'summary' in position: position_text += "\n" + position['summary']
            profile_doc.content.append({'header': 'Position', 'text': position_text})
    if linkedin_dict['educations']['_total'] > 0:
        for education in linkedin_dict['educations']['values']:
            education_text = ""
            if 'fieldOfStudy' in education: education_text += education['fieldOfStudy']
            if 'schoolName' in education: education_text += " at the "+education['schoolName']
            if 'notes' in education: education_text += "\n" + education['notes']
            if 'activities' in education: education_text += "\n\n" + education['activities']
            profile_doc.content.append({'header': 'Education', 'text': education_text})
    if linkedin_dict['recommendations']['_total'] > 0:
        for recommendation in linkedin_dict['recommendations']['values']:
            recommendation_text = recommendation['recommendationText']
            profile_doc.content.append({'header': 'Recommendation', 'text': recommendation_text})
    if 'volunteer' in linkedin_dict:
        if linkedin_dict['volunteer']['volunteerExperiences']['_total'] > 0:
            volexp_text = ""
            for volexp in linkedin_dict['volunteer']['volunteerExperiences']['values']:
                volexp_text += volexp['role'] + " at " + volexp['organization']['name'] + "\n\n"
            profile_doc.content.append({'header': 'Volunteer Experience', 'text': volexp_text})
        if 'supportedOrganizations' in linkedin_dict['volunteer']:
            volsupp_text = ""
            for volsupp in linkedin_dict['volunteer']['supportedOrganizations']['values']:
                volsupp_text += volsupp['name'] + "\n\n"
            profile_doc.content.append({'header': 'Volunteer Support', 'text': volsupp_text})
        if 'causes' in linkedin_dict['volunteer']:
            causes_text = ""
            for cause in linkedin_dict['volunteer']['causes']['values']:
                causes_text += cause['name'] + "\n\n"
            profile_doc.content.append({'header': 'Volunteer Causes', 'text': causes_text})
    if 'courses' in linkedin_dict:
        courses_text = ""
        for course in linkedin_dict['courses']['values']:
            courses_text += course['name'] + "\n\n"
        profile_doc.content.append({'header': 'Courses', 'text': courses_text})

    # save the profile doc to mongo (insert/update)
    linkedin_profile_oid = profile_doc.toMongo()

    return linkedin_profile_oid

def associatePortfoliosWithProfiles(portfolios_dir):
    docdict_list = shareworks.readPortfolios(portfolios_dir)
    print "\nAssociating portfolios with profiles:"
    for doc_dict in docdict_list:
        portfolio_doc = Document(**doc_dict)
        for email in portfolio_doc.student_email:
            try:
                result = db.profile.find_one({"signup.email": email})
                profile = Profile(**result)
            except TypeError:
                print "!?! No profile found for: %s" % email
            else:
                doc_id = portfolio_doc.toMongo()
                if hasattr(profile, 'portfolio'):
                    profile.portfolio.append(doc_id)
                else: profile.portfolio = [doc_id]
                print profile.toMongo(), email, profile.portfolio

def associateWebsitesWithProfiles(websites_dir):
    # this function assumes the indir contains files only
    filelist = os.listdir(websites_dir)
    print "\nAssociating websites with profiles:"
    for fpath in filelist:
        with open(os.path.join(websites_dir, fpath), 'rb') as f:
            doc_dict = json.load(f)
            website_doc = Document(**doc_dict)
            for email in website_doc.student_email:
                result = db.profile.find_one({"signup.email": email})
                profile = Profile(**result)
                doc_id = website_doc.toMongo()
                if hasattr(profile, 'website'):
                    profile.website.append(doc_id)
                else: profile.website = [doc_id]
                print profile.toMongo(), profile.signup['website'], profile.website

# Do a parameter sweep on docs with dev_truth
def devParamSweep(dev_docs, misc_str, start=0):
    dev_runs = []
    for i in range(start, 10):
        conf = float(i)/10
        supp = 20*(i**2)
        # Single (conf, 0), (0.0, supp), (conf, supp)
        prm_str = initializeParameters("single", misc_str, conf, 0)
        dev_runs.append(prm_str)
        for doc in dev_docs: doc.annotate(mongo = False)
        prm_str = initializeParameters("single", misc_str, 0.0, supp)
        dev_runs.append(prm_str)
        for doc in dev_docs: doc.annotate(mongo = False)
        prm_str = initializeParameters("single", misc_str, conf, supp)
        dev_runs.append(prm_str)
        for doc in dev_docs: doc.annotate(mongo = False)
        # Multi (conf, 0), (0.0, supp), (conf, supp)
        prm_str = initializeParameters("multi", misc_str, conf, 0)
        dev_runs.append(prm_str)
        for doc in dev_docs: doc.annotate(mongo = False)
        prm_str = initializeParameters("multi", misc_str, 0.0, supp)
        dev_runs.append(prm_str)
        for doc in dev_docs: doc.annotate(mongo = False)
        prm_str = initializeParameters("multi", misc_str, conf, supp)
        dev_runs.append(prm_str)
        for doc in dev_docs: doc.annotate(mongo = False)
    return dev_runs

def spotterTests():
    ## spotter test
    testdocnl = Document(language='nl', title='NL', _id='nl_test')
    testdocnl.content.append({'text':"kunt u met een joint gitaarspelen Griekse glastuinbouw R&D operationeel onderzoek"})
    testdocen = Document(title='EN', _id='en_test')
    testdocen.content.append({'text':"risky business BoP participatory design contextual analysis of multi-agent system"})
    testdocnl.annotate()
    testdocen.annotate()

def loadJsonInferencesDicts(json_inf_dir, fields_path, transf_inferred=None):
    # this function assumes the indir contains files only
    filelist = os.listdir(json_inf_dir)
    print "\nLoading inferred topics per topic from %s" % json_inf_dir
    inf_per_topic = {}
    for fpath in filelist:
        with open(os.path.join(json_inf_dir, fpath), 'rb') as f:
            inferred_topics = json.load(f)
            if transf_inferred:
                inferred_topics = transf_inferred(inferred_topics)
            inf_per_topic[fpath[:-5]] = inferred_topics
    with open(fields_path, 'rb') as f:
        inf_topic_fields = json.load(f)
    return inf_per_topic, inf_topic_fields

def transformVertexIDs(inferred_topics_dict):
    from urllib2 import unquote as unq
    transformed_dict = {}
    max_flow = max(inferred_topics_dict.itervalues())
    for v_id, flowct in inferred_topics_dict.iteritems():
        unquoted_id = unq(v_id.split("resource/")[1][:-1])
        topic_id = unquoted_id.encode('latin1').decode('utf8')
        transformed_dict[topic_id] = round(flowct/max_flow*100)
    return transformed_dict
    
def produceStatements(all_profiles):
    # N.B. the order in which these operations are performed is essential!
    # Add 'raw, fresh' statements for all profiles
    for pr in all_profiles:
        pr.addStatements("single_dbp_c0_3_s0", "single_p4_c0_2_s0")
    # Get the max raw S,K,I values
    max_ski_dict = maxPerOrigin(all_profiles)
    print "Maximum values per origin:", max_ski_dict
    # Scale the domain of all extracted statements
    for pr in all_profiles:
        pr.scaleStatements(max_ski_dict)
    # Transform all extracted statements to percentiles
    master_lvls_dict = lvlsPerOrigin(all_profiles)
    for pr in all_profiles:
        print "\n\n", pr.signup['email']
        pr.transformStatements(master_lvls_dict)
        print pr.statements["ALL"]['extracted']
    # Load inferred topics from Gremlin JSON output
    dbp_inferences, fields_dbp = loadJsonInferencesDicts(inf_dbpedia_path,
                                                         fields_dbp_path,
                                                         transformVertexIDs)
    for pr in all_profiles:
        # DBpedia inferences
        div, dniv = pr.getDbpediaInferences(dbp_inferences, fields_dbp)
        print "\nInferred DBp In-Vocabulary:"
        for t in div: print t['name'], t['enid'], t['flow']
        print "\nInferred DBp NOT-In-Vocabulary:"
        for t in dniv: print t['name'], t['enid'], t['flow']
        # LinkedIn inferences
        liv, lniv = pr.getLinkedinInferences(names_fields)
        print "\nInferred LI In-Vocabulary:"
        for t in liv: print t['name'], t['enid'], t['count']
        print "\nInferred LI NOT-In-Vocabulary:"
        for t in lniv: print t['name'], None, t['count']
    # Serialize statements to JSON
    PS = []
    for pr in all_profiles:
        p_s = pr.statementsToJSON()
        PS.append(p_s)
    print "Put in pseudosecret.py:", dict(PS)

if __name__ == '__main__' :
    signup_path = "../Phase B/connector/app/db"
    portfolios_path = "../Phase B/sw_portfolios"
    websites_path = "../Phase B/websites"
    inf_dbpedia_path = "../Phase D/flowmaps"
    fields_dbp_path = "../Phase D/niv_fields.json"

    try:
        #readSignups(signup_path)
        #spotterTests()

        # Load docs with dev_truth
        dev_tuswws = loadDocuments({'dev_truth': {'$exists': 1},
                                    'origin': {'$ne': 'linkedin'}})
        dev_li = loadDocuments({'dev_truth': {'$exists': 1},
                                    'origin': 'linkedin'}, LinkedInProfile)
        
        # Load profiles and filter them for non-participants
        all_profiles = loadProfiles()
        all_profiles[:] = [pr for pr in all_profiles if (pr.signup['email'] not in
                                                         {"alex@olieman.net",
                                                          "r.jelierse@student.tudelft.nl"})]
        produceStatements(all_profiles)
        
    finally:
        # disconnect from mongo
        db.connection.disconnect()
