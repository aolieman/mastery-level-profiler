#! /usr/bin/env python
from bs4 import BeautifulSoup
import mechanize, socket, httplib
import os, winsound, urllib2, json
from compare import readVocabulary
from SPARQLWrapper import SPARQLWrapper, JSON

# Create a browser
b = mechanize.Browser()
b.set_handle_robots(False)
b.addheaders = [('User-Agent',
        'Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 6.0;)')]

# list for failed skill pages
failed = []

# initialize NL SPARQL Wrapper
sparql = SPARQLWrapper("http://nl.dbpedia.org/sparql")

# dictionary for manually added URIs (for incorrect URIs, value=good URI or None)
manually_added = {u"name": "uri",
                  u"Audio System Design": "http://en.wikipedia.org/wiki/Sound_recording_and_reproduction",
                  u"Interaction Design": "http://en.wikipedia.org/wiki/Interaction_design",
                  u"Interior Design": "http://en.wikipedia.org/wiki/Interior_design",
                  u"Photography": "http://en.wikipedia.org/wiki/Photography",
                  u"Budgets": "http://en.wikipedia.org/wiki/Budget",
                  u"Wikipedia": "http://en.wikipedia.org/wiki/Wikipedia",
                  u"Overall Wellness": None,
                  u"Product Offerings": None,
                  u"Site Documentation": "http://en.wikipedia.org/wiki/Site_survey",
                  u"Media": "http://en.wikipedia.org/wiki/Media_(communication)",}

# dictionary for manually corrected names (value[1]: get related skills?)
#   (URI is relevant, but name (and related skills) are misleading)
manually_corrected = {u"Billing Systems": (u"Systems", False),
                      u"Adolescent Psychiatry": (u"Adolescence", False),
                      u"China Business Development": (u"China", False),
                      u"Designs": (u"Design", True),
                      u"International": (u"International Experience", False),
                      u"Internal Mobility": (u"Physical Motion", False),
                      u"Natural Lighting": (u"Sunshine", False),
                      u"Opportunity Mapping": (u"Opportunity Cost", False),
                      u"Modelling Tools": (u"Scientific Modelling", True),
                      u"Statistical Tools": (u"Tools", False),
                      u"Dollar Universe": (u"Universe", False)}

# get the links on this page from the directory list
def getDirectoryLinks( url ):
    b.open(url)
    soup = BeautifulSoup(b.response().get_data(), "lxml")
    directory_links = []
    
    ul_dir = soup.find("ul", "directory")
    atags = ul_dir.find_all("a")
    for atag in atags:
        unicode_name = unicode(atag.string)
        directory_links.append((atag['href'], unicode_name))
    return directory_links

def visitDirectories(start=0, end=27, start_subdir=0):
    alpha_list = map(chr, range(97, 123))
    alpha_list.append('%40')
    base_dir = 'http://www.linkedin.com/skills/directory/'
    # get links to sub-directories (respecting given range)
    alpha_list = alpha_list[start:end]
    for alpha in alpha_list:
        subdir_links = getDirectoryLinks(base_dir + alpha)
        print "## Opened main directory " + alpha
        # get links to skills from sub-directories (respecting start)
        if alpha == alpha_list[0]:
            subdir_links = subdir_links[start_subdir:]
        for subdir in subdir_links:
            skill_links = getDirectoryLinks(subdir[0])
            print "## Opened sub-directory " + subdir[1]
            saveSkills(skill_links)

def saveSkills( skill_tuples ):
    
    for skill_tuple in skill_tuples:
        skill_URL = skill_tuple[0]
        skill_name = fixFilename(skill_tuple[1])
        local_path = 'vocabulary/'
        try:
            b.open(skill_URL)
            soup = BeautifulSoup(b.response().get_data(), "lxml")
        except mechanize.HTTPError:
            print "-Failed: " + skill_tuple[1]
            print "--HTTP error"
            failed.append(skill_tuple)
        except mechanize.URLError as e:
            print "-Failed: " + skill_tuple[1]
            print "--URL error({0}): {1}".format(e.errno, e.strerror)
            failed.append(skill_tuple)
        else:
            output = open(local_path + skill_name + ".html", "w")
            print "Writing: " + skill_tuple[1]
            output.write(soup.prettify().encode('utf-8'))
            winsound.PlaySound('heartbeat.wav', winsound.SND_FILENAME)
            output.close()

def fixFilename(name):
    filename = ''
    for char in name:
        if not (char in '<>:"/\|?*'):
            if ord(char)>31:
                filename += char
        else: filename += '_'
    return filename

def saveElements(indir, outfile, verbose=None):
    # this function assumes the indir contains files only
    filelist = os.listdir(indir)    
    vocabulary = []
    for f in filelist:
        skillpage = open(os.path.join(indir, f), "r")
        soup = BeautifulSoup(skillpage, "lxml")
        skill = {}
        process_summary = True
        # find the name and summary
        wiki_blurb = soup.find('div', 'wiki-blurb')
        skill['name'] = wiki_blurb.find('h2').string.strip()
        if skill['name'] in manually_added: #Note: not tested!
            skill['more_wiki'] = manually_added[skill['name']]
            if skill['more_wiki'] == None:
                del skill['more_wiki'] # the uri was incorrect, so delete the key
                process_summary = False # and make sure it isn't set again
        growth_rate = wiki_blurb.find('span', 'growth-rate')
        if growth_rate: skill['growth_rate'] = growth_rate.string.strip()
        skill['primary_industry'] = wiki_blurb.find('p', 'primary-industry').string.strip()
        skill_summary = wiki_blurb.find('p', 'skill-summary')
        skill['summary'] = None
        if skill_summary and process_summary:
            skill['summary'] = " ".join([string for string in skill_summary.stripped_strings]).split(u'\u2026', 1)[0]
            skill_links = skill_summary.find_all('a')
            skill_links = [link.get('href') for link in skill_links]
            skill['more_wiki'] = urllib2.unquote(skill_links[len(skill_links)-1][20:-13])
            skill['skill_links'] = skill_links[:-1]

        if skill['name'] in manually_corrected: #Note: not tested!
            skill['name'] = manually_corrected[skill['name']][0]
            if manually_corrected[skill['name']][1]: # rel skills are applicable
                skill['related_skills'] = findRelSkills(soup)
        else:
            skill['related_skills'] = findRelSkills(soup)

        vocabulary.append(skill)

        if verbose:
            print '\n'+skill['name']
            if 'growth_rate' in skill: print skill['growth_rate']
            if 'primary_industry' in skill: print skill['primary_industry']
            if 'related_skills' in skill: print skill['related_skills']
            if skill['summary']:
                print skill['summary']
                if len(skill['skill_links']) > 0: print skill['skill_links']
                print skill['more_wiki']

    ofile = open(outfile, 'wb')
    json.dump(vocabulary, ofile, indent=4, separators=(',', ': '))
    ofile.close()

# Find related skills from a skill page
def findRelSkills(soup):
    rel_a_list = soup.find_all('a', 'skills-list-skill')
    rel_links = []
    for rel_a in rel_a_list:
        pagelink = rel_a.get('href').split('/')[-1]
        rel_links.append(urllib2.unquote(pagelink.split('?')[0]))
    return rel_links

def interlanguageWiki(vocab_dict, verbose=0):
    for (count, term) in enumerate(vocab_dict):
        if u'more_wiki' in term:
            term_id = term[u'more_wiki'].split('wiki/')[-1]
            sparql.setQuery("""
                SELECT ?nluri
                WHERE {?nluri owl:sameAs <http://dbpedia.org/resource/%s> .}
            """ % (term_id, ))
            sparql.setReturnFormat(JSON)
            results = sparql.query().convert()
            res_bindings = results['results']['bindings']
            if verbose > 1:
                print len(res_bindings), term_id
            if len(res_bindings) == 0: continue
            elif len(res_bindings) > 1:
                raise Exception("More than one interlanguage link!")
            nl_uri = res_bindings[0]['nluri']['value']
            term[u'nl_uri'] = nl_uri
            if verbose > 0: print count, nl_uri
    return vocab_dict
        

if __name__ == '__main__' :

##    saveElements('vocabulary/', 'vocabulary_rel.json', verbose='y')
##    vocabulary = readVocabulary('vocabulary_rel.json')
##    vocab_dutch = interlanguageWiki(vocabulary, verbose=1)
##    ofile = open('vocabulary_nl.json', 'wb')
##    json.dump(vocab_dutch, ofile, indent=4, separators=(',', ': '))
##    ofile.close()
    pass
