import groovy.json.*

// Initialize DBpedia graph
g = new LinkedDataSailGraph(new NativeStoreSailGraph( '../../dbpedia' ))
g.addNamespace( 'dbp', 'http://dbpedia.org/resource/')
g.addDefaultNamespaces()

// Define categories to ignore
ign = [g.uri('dbp:Category:Management'), g.uri('dbp:Category:Production_and_manufacturing'), g.uri('dbp:Category:Manufacturing'), g.uri('dbp:Category:Business_terms'),
       g.uri('dbp:Category:Language'), g.uri('dbp:Category:Humanities'), g.uri('dbp:Category:Methodology'), g.uri('dbp:Category:Engineering'), g.uri('dbp:Category:Operations_research'),
       g.uri('dbp:Category:Style_guides'), g.uri('dbp:Category:Industry'), g.uri('dbp:Category:Inventory')]

def saveFlow( enid ){
    // Process one topic URI
    v = g.v( "http://dbpedia.org/resource/$enid" )
    println "\n\n" // print categories of which v is a member
    println v
    println v.out( 'dcterms:subject' ).out( 'rdfs:label' ).toList()
    // Count flow (Sibling, Narrower, Broader, and Cousin topics)
    flow = [:] // (NB: don't forget to iterate over pipes)
    v.out( 'dcterms:subject' ).filter{!ign.contains(it.id)}.in( 'dcterms:subject' ).groupCount(flow){it}{it.b+1.0}.iterate() // Sibling w1.0
    v.out( 'dcterms:subject' ).filter{!ign.contains(it.id)}.both( 'skos:broader' ).filter{!ign.contains(it.id)}.in( 'dcterms:subject' ).groupCount(flow){it}{it.b+0.5}.iterate() // Narrower & Broader w0.5
    v.out( 'dcterms:subject' ).filter{!ign.contains(it.id)}.in( 'skos:broader' ).filter{!ign.contains(it.id)}.out( 'skos:broader' ).in( 'dcterms:subject' ).groupCount(flow){it}{it.b+0.25}.iterate() // Cousin-via-Narrower w0.25
    //v.out( 'dcterms:subject' ).filter{!ign.contains(it.id)}.out( 'skos:broader' ).filter{!ign.contains(it.id)}.in( 'skos:broader' ).in( 'dcterms:subject' ).groupCount(flow){it}{it.b+0.25}.iterate() // Cousin-via-Broader w0.25
    // Sort and serialize to JSON
    max_topics = 350
    if (flow.size() < max_topics){max_topics = flow.size()}
    flow_sorted = flow.sort{ a,b -> b.value <=> a.value }[0..max_topics-1]
    println "\n\n" // print top 20 results, else raise exception
    println flow_sorted.subMap((flow_sorted.keySet() as List)[0..19])
    def jbuilder = new JsonBuilder()
    jbuilder(flow_sorted)
    ofile = new File( "../../flowmaps/${enid}.json" )
    ofile.write(JsonOutput.prettyPrint(jbuilder.toString()))
}

// Load a JSON list of extracted topics
def jslurper = new JsonSlurper()
new File( "../../extracted_topics.json" ).withReader { ireader ->
    extracted_topics = jslurper.parse(ireader)
}

failed_topics = [ "Estimation", "Human_factors", "Persian_language", "Web_2.0" ]

// Save flow for all extracted topics
failed = [:]
try {
    for (enid in extracted_topics){
        try {
            saveFlow(enid)
        } catch (e){ failed[enid] = e }
    }
} finally {
    // Persist graph changes to disk
    g.getRawGraph().getBaseSail().shutDown()
    println "\n\n"
    println failed
}

