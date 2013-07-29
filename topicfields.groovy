import groovy.json.*

// Initialize DBpedia graph
g = new LinkedDataSailGraph(new NativeStoreSailGraph( '../../dbpedia' ))
g.addNamespace( 'dbp', 'http://dbpedia.org/resource/')
g.addDefaultNamespaces()

def getFields( enid ){
    // Process one topic URI
    v = g.v( "http://dbpedia.org/resource/$enid" )
    topic_fields = [:]
    topic_fields['label'] = v.out( 'rdfs:label' ).filter{it.lang=="en"}.value.toList()[0]
    topic_fields['summary'] = v.out( 'rdfs:comment' ).filter{it.lang=="en"}.value.toList()[0]
    topic_fields['wikilink'] = v.out( 'foaf:isPrimaryTopicOf' ).id.toList()[0]
    fields_map[enid] = topic_fields
    println "\n\n" // print fields
    println v
    println topic_fields
}

not_in_vocabulary = ['Work_of_art', 'Critical_to_quality', 'Living_lab', 'Modern_typography', 'Sycophancy', 'Design_comics', 'Belief',
                     'C-K_theory', 'Human-centered_computing', 'Intelligence-based_design', 'Knowledge_spillover', 'Hypothesis', 'New_Wave_(design)',
                     'Slow_design', 'Urban_acupuncture', 'Safety_assurance', 'Form_follows_function', 'Presentation%E2%80%93abstraction%E2%80%93control',
                     'Process-centered_design', 'Epiphany_(feeling)', 'Sensory_design', 'Lean_integration', 'System_usability_scale', 'Psychical_distance',
                     'Cognitive_complexity', 'Immersive_design', 'Architect-led_design%E2%80%93build', 'Sonic_interaction_design', 'Affective_design']

// Save metadata fields for top inferred topics that are not in the LI vocabulary
fields_map = [:]
failed = [:]
try {
    for (enid in not_in_vocabulary){
        try {
            getFields( enid )
        } catch (e){ failed[enid] = e }
    }
    println fields_map
    def jbuilder = new JsonBuilder()
    jbuilder(fields_map)
    ofile = new File( "../../niv_fields.json" )
    ofile.write(JsonOutput.prettyPrint(jbuilder.toString()))
} finally {
    // Persist graph changes to disk
    g.getRawGraph().getBaseSail().shutDown()
    println "\n\n"
    println failed
}

