#!/usr/bin/env python
import pymongo, os, json
import nltk.tokenize, nltk.stem
import compare, tudelft, shareworks

# set up annotation functions
vocabulary = compare.readVocabulary('vocabulary_man.json')
term_ids, nl_dict, en_dict = compare.getTermIDs(vocabulary)

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
ignored_ann_ids = {"Academic_term", "Code", "Consideration", "Course_(education)",
                   "College", "Diploma", "Further_education", "Hobby", "Home",
                   "Human", "Job_(role)", "Life", "Laborer", "Privately_held_company",
                   "Printing", "Professor", "Safe", "School", "Prostitution",
                   "Secondary_education", "Solution", "Student", "Supervisor",
                   "Theory", "Tutorial", "University", "Van", "Vocational_education"}
# set of ann_ids that occur in course descriptions, but don't say much about the course
ignored_tudelft = {"Blackboard_Learning_System", "Education", "Blackboard_Inc~",
                   "Deliverable", "Demand_(economics)", "Epistemology", "Feedback",
                   "Higher_education", "Lecture", "Literature", "Material",
                   "Master_class", "Print_on_demand", "Reference", "Summary",
                   "Email", "Homework", "Training", "Symposium", "Engineer"}
# set of ann_ids that occur in portfolios/websites, but don't say much about the project/student
ignored_shw_web = {"Deliverable", "Education", "Female", "Graduation",
                   "Image", "Male", "Output", "Project", "Woman"}

# Translation dict (ann_id->ann_id) for domain-specific abbreviations
ide_abbr = {"Integrated_development_environment": "Product_design",
            "Very_Important_Person": "Vision_in_Product_Design"}

class Profile(object):
    def __init__(self, **entries):
        self.__dict__.update(entries)

    def toMongo(self):
        return db.profile.save(self.__dict__)

    def addStatements(self, param_str): # TODO: differing param_str per language
        # Initialize empty StatementDicts
        all_ext, tu_ext = StatementDict(), StatementDict()
        sw_ext, ws_ext = StatementDict(), StatementDict()
        # Get LinkedIn StatementDict, if available
        try:
            li_doc = LinkedInProfile(**db.document.find_one({"_id": self.linkedin}))
        except AttributeError:
            print "!! %s has not connected LinkedIn" % self.signup['email']
            li_ext = StatementDict()
        else:
            try:
                li_ext = StatementDict(getattr(li_doc, param_str)['extracted'])
                all_ext.update(li_ext)
            except AttributeError:
                print "!! %s has no statements for %s" % (li_doc.title, param_str)
                li_ext = StatementDict()
                li_doc.makeStatements(param_str)
        # Get statements for each course description
        for course_doc in self.iterTUDocs():
            try:
                doc_ext = StatementDict(getattr(course_doc, param_str)['extracted'])
                tu_ext.update(doc_ext)
                all_ext.update(doc_ext)
            except AttributeError:
                print "!! %s has no statements for %s" % (course_doc.title, param_str)
                course_doc.makeStatements(param_str)
        # Get statements for each portfolio document
        for sw_doc in self.iterPortfolioDocs():
            try:
                doc_ext = StatementDict(getattr(sw_doc, param_str)['extracted'])
                sw_ext.update(doc_ext)
                all_ext.update(doc_ext)
            except AttributeError:
                print "!! %s has no statements for %s" % (sw_doc._id, param_str)
                sw_doc.makeStatements(param_str)
        # Get statements for each website document
        for webpage in self.iterWebsiteDocs():
            try:
                doc_ext = StatementDict(getattr(webpage, param_str)['extracted'])
                ws_ext.update(doc_ext)
                all_ext.update(doc_ext)
            except AttributeError:
                print "!! %s has no statements for %s" % (webpage.title, param_str)
                webpage.makeStatements(param_str)
            
        self.statements = {'linkedin': {'extracted': li_ext, 'inferred': []},
                           'tudelft': {'extracted': tu_ext, 'inferred': []},
                           'shareworks': {'extracted': sw_ext, 'inferred': []},
                           'website': {'extracted': ws_ext, 'inferred': []},
                           'ALL': {'extracted': all_ext, 'inferred': []}}

        # TODO: Save profile to Mongo


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
        for course_doc in self.iterTUDocs():
            # check if the document has been annotated
            if text_ann not in course_doc.content[0]:
                course_doc.annotate(title=True)
            else: print course_doc.title, "has already been annotated"
        # Annotate webpage documents
        for webpage in self.iterWebsiteDocs():
            # check if the document has been annotated
            if text_ann not in page.content[0]:
                page.annotate()
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
                course_doc = tudelft.courseDoc(course['cursusid'], course['collegejaar'])
                if course_doc == None: continue
                yield course_doc

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

    def makeStatements(self, param_str, del_resp=False):
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
            print fK, know_terms
            print fS, skill_terms
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
                    extracted.add(statement(ann_id, fS*2, fK*2, 1.0))
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

def statement(ann_id, skill=0.0, knowledge=0.0, interest=0.0):
    lvl_dict = {'skill': skill, 'knowledge': knowledge, 'interest':interest}
    return (ann_id, lvl_dict)

class StatementDict(dict):
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

if __name__ == '__main__' :
    signup_path = "../Phase B/connector/app/db"
    portfolios_path = "../Phase B/sw_portfolios"
    websites_path = "../Phase B/websites"

    try:
        #readSignups(signup_path)
        profiles = loadProfiles()

        #spotterTests()

        dev_tuswws = loadDocuments({'dev_truth': {'$exists': 1},
                                    'origin': {'$ne': 'linkedin'}})
        dev_li = loadDocuments({'dev_truth': {'$exists': 1},
                                    'origin': 'linkedin'}, LinkedInProfile)

    finally:
        # disconnect from mongo
        db.connection.disconnect()
