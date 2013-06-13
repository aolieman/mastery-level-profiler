#!/usr/bin/env python
import pymongo, os, json
import compare, tudelft

# set up annotation functions
vocabulary = compare.readVocabulary('vocabulary_nl.json')
term_ids = compare.getTermIDs(vocabulary)
confidence = 0.0
support = 0
parameter_str = '_c%s_s%s' % (str(confidence).replace('.', '_'), support)
title_ann = 'title_ann' + parameter_str
title_resp = 'title_resp' + parameter_str
header_ann = 'h_ann' + parameter_str
header_resp = 'h_resp' + parameter_str
text_ann = 'txt_ann' + parameter_str
text_resp = 'txt_resp' + parameter_str

# establish a connection to the MongoDB
db = pymongo.Connection('localhost', 27017)['mastery_level_profiler']

class Profile(object):
    def __init__(self, **entries):
        self.__dict__.update(entries)

    def toMongo(self):
        return db.profile.save(self.__dict__)

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
        else: print "!! "+self.signup['email']+" has not connected LinkedIn"

    def annotateDocs(self):
        if hasattr(self, 'linkedin'):
            li_profile = LinkedInProfile(**db.document.find_one({"_id": self.linkedin}))
            # check if the document has been annotated
            if text_ann not in li_profile.content[0]:
                li_profile.annotate()
            else: print li_profile.title, "has already been annotated"
        else: print "!! "+self.signup['email']+" has not connected LinkedIn"
        if self.tudelft == None:
            print "!! %s has not connected TU Delft" % (self.signup['email'], )
        else:
            for course in self.tudelft:
                course_doc = tudelft.courseDoc(course['cursusid'], course['collegejaar'])
                if course_doc == None: continue
                # check if the document has been annotated
                if text_ann not in course_doc.content[0]:
                    course_doc.annotate(title=True)
                else: print course_doc.title, "has already been annotated"
        print "Annotations for "+self.signup['email']+" are done"

class Document(object):
    def __init__(self, **entries):
        self.language = "en"
        self.content = []
        self.__dict__.update(entries)

    def toMongo(self):
        return db.document.save(self.__dict__)

    def annotate(self, header=False, text=True, title=False):
        print "Annotations for " + self.title
        if title:
            sp_tuple = compare.throughSpotlight(self.title, confidence, support, 'en')
            if sp_tuple == None:
                pass
            else:
                setattr(self, title_ann, sorted(list(set(sp_tuple[0]).intersection(term_ids))))
                print getattr(self, title_ann)
                setattr(self, title_resp, sp_tuple[1])
        for section in self.content:
            if header:
                if len(section['header']) > 3:
                    sp_tuple = compare.throughSpotlight(section['header'], confidence, support, self.language)
                    if sp_tuple == None:
                        pass
                    else:
                        section[header_ann] = sorted(list(set(sp_tuple[0]).intersection(term_ids)))
                        print section[header_ann]
                        section[header_resp] = sp_tuple[1]
            if text:
                if len(section['text']) > 3: #quickfix for empty strings
                    sp_tuple = compare.throughSpotlight(section['text'], confidence, support, self.language)
                    if sp_tuple == None:
                        continue
                    else:
                        section[text_ann] = sorted(list(set(sp_tuple[0]).intersection(term_ids)))
                        print section[text_ann]
                        section[text_resp] = sp_tuple[1]
        self.toMongo()

class UnequalIDsException(pymongo.errors.InvalidId):
    pass

class LinkedInProfile(Document):
    pass

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
        signup_file.close
        # make object, make linkedin doc, and insert to mongo
        new_profile = Profile(signup=signup, tudelft=tudelft)
        new_profile.updateLinkedInDoc()
        print new_profile.toMongo()

def loadProfiles(): #from mongo
    result = db.profile.find()
    profiles = [Profile(**res) for res in result]
    return profiles

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
            profile_doc.content.append({'header': 'Recommedation', 'text': recommendation_text})
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

if __name__ == '__main__' :
    signup_path = "../Phase B/connector/app/db"
    readSignups(signup_path)
    profiles = loadProfiles()

    # disconnect from mongo
    db.connection.disconnect()
