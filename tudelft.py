#!/usr/bin/env python
import json, urllib2, time
import pymongo

# establish a connection to the MongoDB
db = pymongo.Connection('localhost', 27017)['mastery_level_profiler']

# format string query
query = "http://api.tudelft.nl/v0/vakken/%s?studiejaarid=%s"

# studiejaar translation
yeardict = {'2005': '1', '2006': '3', '2007': '4', '2008': '5',
            '2009': '6', '2010': '7', '2011': '8', '2012': '9'}

def getCourse(course_id, year):
    f_query = query % (course_id, yeardict[year])
    incr = 0
    while incr < 3:
        try:
            response = json.loads(urllib2.urlopen(f_query).read())
            break
        except UnicodeDecodeError, err:
            print err
            print "Trying %s again..." % (f_query, )
            time.sleep(2)
            incr += 1
    else: return None # fetching failed
    if response == None: return None # fetching failed
    try:
        title = response['vak']['langenaamEN']
        result = response['vak']['extraUnsupportedInfo']
    except KeyError, TypeError:
        print "FAILED:", f_query
        return None
    else:
        response['_id'] = "%sy%s" % (course_id, year)
        db.course_description.save(response)
        return title, result['vakUnsupportedInfoVelden']

def courseDoc(course_id, year):
    doc_in_mongo = db.document.find_one({"_id": "%sy%s" % (course_id, year)})
    if doc_in_mongo:
        return Document(**doc_in_mongo)
    else:
        course_info = getCourse(course_id, year)
        if course_info == None: return None
        title, info = course_info
        course_doc = Document(doctype="course", origin="tudelft")
        course_doc._id = "%sy%s" % (course_id, year)
        course_doc.title = title
        for field in info:
            if len(field['inhoud']) > 30:
                course_doc.content.append({'header': field['@label'], 'text': field['inhoud']})
        # save the profile doc to mongo (insert/update)
        course_description_oid = course_doc.toMongo()
        return course_doc

#circular import
from complete_profile import Document

if __name__ == '__main__' :

    
    
    # disconnect from mongo
    db.connection.disconnect()
