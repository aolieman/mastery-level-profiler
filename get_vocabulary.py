#! /usr/bin/env python
from bs4 import BeautifulSoup
import mechanize, socket, httplib
import os, winsound, urllib2, json

# Create a Browser
b = mechanize.Browser()
b.set_handle_robots(False)
b.addheaders = [('User-Agent',
        'Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 6.0;)')]


# list for failed skill pages
failed = []

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
        # find the name and summary
        wiki_blurb = soup.find('div', 'wiki-blurb')
        skill['name'] = wiki_blurb.find('h2').string.strip()
        growth_rate = wiki_blurb.find('span', 'growth-rate')
        if growth_rate: skill['growth_rate'] = growth_rate.string.strip()
        skill['primary_industry'] = wiki_blurb.find('p', 'primary-industry').string.strip()
        skill_summary = wiki_blurb.find('p', 'skill-summary')
        skill['summary'] = None
        if skill_summary:
            skill['summary'] = " ".join([string for string in skill_summary.stripped_strings]).split(u'\u2026', 1)[0]
            skill_links = skill_summary.find_all('a')
            skill_links = [link.get('href') for link in skill_links]
            skill['more_wiki'] = urllib2.unquote(skill_links[len(skill_links)-1][20:-13])
            skill['skill_links'] = skill_links[:-1]

        vocabulary.append(skill)

        if verbose:
            print '\n'+skill['name']
            print skill['growth_rate']
            print skill['primary_industry']
            if skill['summary']:
                print skill['summary']
                if len(skill['skill_links']) > 0: print skill['skill_links']
                print skill['more_wiki']

    ofile = open(outfile, 'wb')
    json.dump(vocabulary, ofile, indent=4, separators=(',', ': '))
    ofile.close()

if __name__ == '__main__' :

    saveElements('vocabulary/', 'vocabulary_wsp.json')

