#!/usr/bin/env python
import json, urllib2, time
import pymongo
import complete_profile

# establish a connection to the MongoDB
db = pymongo.Connection('localhost', 27017)['mastery_level_profiler']

# format string query
query = "http://api.tudelft.nl/v0/vakken/%s?studiejaarid=%s"

# studiejaar translation
yeardict = {'2004': '1', '2005': '1', '2006': '3', '2007': '4', '2008': '5',
            '2009': '6', '2010': '7', '2011': '8', '2012': '9'}

def getCourse(course_id, year):
    f_query = query % (course_id, yeardict[year])
    attempt_count = 0
    while attempt_count < 3:
        try:
            http_resp = urllib2.urlopen(f_query).read()
            response = json.loads(http_resp.decode('cp1252'))
            break
        except UnicodeDecodeError, err:
            print err
            print "Trying %s again..." % (f_query, )
            time.sleep(5)
            attempt_count += 1
    else: return None # fetching failed
    if response == None: return None # fetching failed
    try:
        title = response['vak']['langenaamEN']
        result = response['vak']['extraUnsupportedInfo']
    except KeyError, TypeError:
        print "FAILED:", f_query
        return None
    else:
        if 'vakUnsupportedInfoVelden' in result:            
            response['_id'] = "%sy%s" % (course_id, year)
            db.course_description.save(response)
            return title, result['vakUnsupportedInfoVelden']
        else:
            print "\nNOT USABLE??\n"
            print response
            return None # no fields in response

def courseDoc(course_id, year):
    doc_in_mongo = db.document.find_one({"_id": "%sy%s" % (course_id, year)})
    if doc_in_mongo:
        return complete_profile.Document(**doc_in_mongo)
    else:
        course_info = getCourse(course_id, year)
        if course_info == None: return None
        title, info = course_info
        course_doc = complete_profile.Document(doctype="course", origin="tudelft")
        course_doc._id = "%sy%s" % (course_id, year)
        course_doc.title = title
        for field in info:
            if len(field['inhoud']) > 30:
                course_doc.content.append({'header': field['@label'], 'text': field['inhoud']})
        if len(course_doc.content) == 0:
            course_doc.content = [{'text': 'FrozenCutlery', 'txt_ann': None}]
        # save the profile doc to mongo (insert/update)
        course_description_oid = course_doc.toMongo()
        return course_doc

# Old solution for circular import (new solution untested!)
#from complete_profile import Document

if __name__ == '__main__' :

    
    
    # disconnect from mongo
    db.connection.disconnect()
