from dotenv import load_dotenv
from sqlalchemy import create_engine, URL
from neo4j import GraphDatabase
from pathlib import Path
import pandas as pd
import os

# ================================================
# LOAD .env
# ================================================

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# ================================================
# CONNECTIONS
# ================================================

pg_url = URL.create(
    drivername="postgresql+psycopg2",
    username=os.getenv('DPM_USER'),
    password=os.getenv('DPM_PASSWORD'),
    host=os.getenv('DPM_HOST'),
    port=int(os.getenv('DPM_PORT')),
    database=os.getenv('DPM_DB')
)
db_engine = create_engine(pg_url)

neo4j_driver = GraphDatabase.driver(
    os.getenv('NEO4J_URI'),
    auth=(os.getenv('NEO4J_USER'), os.getenv('NEO4J_PASSWORD'))
)

# ================================================
# EXTRACT FROM POSTGRESQL
# ================================================

# ReasonCategory nodes
categories = pd.read_sql("""
    SELECT DISTINCT reason_category_name AS name
    FROM staging.reason_tree
    WHERE reason_category_name IS NOT NULL
                         ORDER BY name
""", db_engine)

# ReasonTree nodes + HAS_REASON_TREE
trees = pd.read_sql("""
    SELECT DISTINCT
        reason_category_name AS category_name,
        name AS tree_name,
        description,
        enabled
    FROM staging.reason_tree
""", db_engine)

# All Reason nodes including intermediates
reasons = pd.read_sql("""
    SELECT name, display_name, display_name_token AS token,
           description, FALSE AS is_intermediate
    FROM staging.reason

    UNION

    SELECT DISTINCT
        rtn.reason_name AS name,
        rtn.reason_name AS display_name,
        NULL AS token,
        NULL AS description,
        TRUE AS is_intermediate
    FROM staging.reason_tree_node rtn
    WHERE rtn.final_reason = FALSE
    AND rtn.reason_name NOT IN (SELECT name FROM staging.reason)

    ORDER BY name
""", db_engine)

# MODEL NODES (called Workunit in Neo4j graph)
models = pd.read_sql("""
    SELECT DISTINCT model_name
    FROM staging.model_reason_tree_link
""", db_engine)

# CONTAINS_REASON relationships (link between reason tree and reason. Reason_trees contain reasons)
contains = pd.read_sql("""
    SELECT
        rtn.reason_tree_name AS tree_name,
        rtn.reason_name,
        rtn.final_reason,
        rtn.enabled
    FROM staging.reason_tree_node rtn
    WHERE rtn.parent_reason_name IS NULL
    ORDER BY tree_name, reason_name
""", db_engine)

# HAS_REASON_CHILD relationships (for intermediate reasons that are not final)
children = pd.read_sql("""
    SELECT
        rtn.parent_reason_name,
        rtn.reason_name,
        rtn.reason_tree_name AS tree_context,
        rtn.final_reason,
        rtn.enabled
    FROM staging.reason_tree_node rtn
    WHERE rtn.parent_reason_name IS NOT NULL
    ORDER BY tree_context, parent_reason_name, reason_name
""", db_engine)

#Called Workunit in Neo4j Graph
model_reason_links = pd.read_sql("""
    SELECT
        model_name,
        reason_tree_name
    FROM staging.model_reason_tree_link
""", db_engine)

# MachineCode — HAS_POSSIBLE_REASON relationships (Each workunit has a possible reason of failure)
machine_codes = pd.read_sql("""
    SELECT 
        model_name,
        reason_name,
        reason_tree_name,
        name        AS display_name,
        description,
        code_value
    FROM staging.machine_code
    ORDER BY model_name, code_value
""", db_engine)

print(f"  {len(machine_codes)} HAS_POSSIBLE_REASON relationships")

#Relationship that points from workunit to work center
workunit_links = pd.read_sql("""
    SELECT
        name            AS workunit_name,
        description,
        thing_name,
        is_pacemaker,
        workcenter_name
    FROM staging.workunit
    ORDER BY workcenter_name, name
""", db_engine)

# WorkCenter nodes
workcenters = pd.read_sql("""
    SELECT
        name,
        description,
        thing_name,
        target_oee,
        area_name
    FROM staging.workcenter
    ORDER BY name
""", db_engine)

areas = pd.read_sql("""
        SELECT
            name,
            description,
            thing_name,
            site_name
            FROM staging.area
            ORDER BY name
""", db_engine)

# WorkCenter to Area link (for HAS_WORKCENTER relationship)
workcenter_links = pd.read_sql("""
    SELECT
        name            AS workcenter_name,
        area_name
    FROM staging.workcenter
    ORDER BY area_name, name
""", db_engine)

# Site nodes
sites = pd.read_sql("""
    SELECT
        name,
        description,
        thing_name,
        target_oee,
        time_zone,
        region_name
    FROM staging.site
    ORDER BY name
""", db_engine)



# Area to Site link (for HAS_AREA relationship)
area_links = pd.read_sql("""
    SELECT
        name        AS area_name,
        site_name
    FROM staging.area
    ORDER BY site_name, name
""", db_engine)

#Enterprise node
enterprises = pd.read_sql("""
    SELECT
        name,
        description,
        thing_name,
        is_default_enterprise
    FROM staging.enterprise
""", db_engine)

#Site to Enterprise link (HAS_SITE relationship)
site_links = pd.read_sql("""
    SELECT
        s.name          AS site_name,
        e.name          AS enterprise_name
    FROM staging.site s
    CROSS JOIN staging.enterprise e
""", db_engine)

# Create ALL WorkUnit nodes from staging.workunit
all_workunits = pd.read_sql("""
        SELECT
            name,
            description,
            thing_name,
            is_pacemaker,
            workcenter_name
        FROM staging.workunit
        ORDER BY name
    """, db_engine)




print(f"Extracted:")
print(f"  {len(categories)} ReasonCategory nodes")
print(f"  {len(trees)} ReasonTree nodes")
print(f"  {len(reasons)} Reason nodes")
print(f"  {len(contains)} CONTAINS_REASON relationships")
print(f"  {len(children)} HAS_REASON_CHILD relationships")
print(f"  {len(workunit_links)} WorkUnit records")
print(f"  {len(workcenters)} WorkCenter nodes")
print(f"  {len(areas)} Area nodes")
print(f"  {len(workcenter_links)} HAS_WORKCENTER relationships")
print(f"  {len(sites)} Site nodes")
print(f"  {len(area_links)} HAS_AREA relationships")
print(f"  {len(enterprises)} Enterprise nodes")
print(f"  {len(site_links)} HAS_SITE relationships")


# ================================================
# LOAD INTO NEO4J
# ================================================

with neo4j_driver.session(database="DPM") as session:

    # Step 1: ReasonCategory nodes
    print("\nCreating ReasonCategory nodes...")
    for _, row in categories.iterrows():
        session.run("""
            MERGE (:ReasonCategory {name: $name})
        """, name=row['name'])
    print(f"  Done — {len(categories)} nodes")

    # Step 2: ReasonTree nodes + HAS_REASON_TREE relationships
    print("Creating ReasonTree nodes and HAS_REASON_TREE relationships...")
    for _, row in trees.iterrows():
        if pd.notna(row['category_name']):
            session.run("""
                MERGE (t:ReasonTree {name: $tree_name})
                SET t.description = $description,
                    t.enabled = $enabled
                WITH t
                MATCH (c:ReasonCategory {name: $category_name})
                MERGE (c)-[:HAS_REASON_TREE]->(t)
            """,
        tree_name=row['tree_name'],
        description=row['description'],
        enabled=bool(row['enabled']) if pd.notna(row['enabled']) else False,
        category_name=row['category_name'])
        else:
            # Running and Unknown Fault have no category
            session.run("""
                MERGE (t:ReasonTree {name: $tree_name})
                SET t.description = $description,
                    t.enabled = $enabled
            """,
            tree_name=row['tree_name'],
            description=row['description'],
            enabled=bool(row['enabled']) if pd.notna(row['enabled']) else False)
        
    # Step 3: Reason nodes
    print("Creating Reason nodes...")
    for _, row in reasons.iterrows():
        session.run("""
            MERGE (r:Reason {name: $name})
            SET r.displayName = $display_name,
                r.displayNameToken = $token,
                r.description = $description,
                r.isIntermediate = $is_intermediate
        """,
        name=row['name'],
        display_name=row['display_name'] if pd.notna(row['display_name']) else None,
        token=row['token'] if pd.notna(row['token']) else None,
        description=row['description'] if pd.notna(row['description']) else None,
        is_intermediate=bool(row['is_intermediate']))
    print(f"  Done — {len(reasons)} nodes")

    # After loading all Reason nodes, fix isIntermediate based on graph structure
    print("Fixing isIntermediate properties...")
    session.run("""
        MATCH (r:Reason)-[:HAS_REASON_CHILD]->(:Reason)
        SET r.isIntermediate = true
    """)
    print("  Done")

    # Step 4: CONTAINS_REASON relationships
    print("Creating CONTAINS_REASON relationships...")
    for _, row in contains.iterrows():
        session.run("""
            MATCH (t:ReasonTree {name: $tree_name})
            MATCH (r:Reason {name: $reason_name})
            MERGE (t)-[:CONTAINS_REASON {finalReason: $final, enabled: $enabled}]->(r)
        """,
        tree_name=row['tree_name'],
        reason_name=row['reason_name'],
        final=bool(row['final_reason']),
        enabled=bool(row['enabled']))
    print(f"  Done — {len(contains)} relationships")

    # Step 5: HAS_REASON_CHILD relationships
    print("Creating HAS_REASON_CHILD relationships...")
    for _, row in children.iterrows():
        session.run("""
            MATCH (parent:Reason {name: $parent_name})
            MATCH (child:Reason {name: $child_name})
            MERGE (parent)-[:HAS_REASON_CHILD {treeContext: $tree_context, enabled: $enabled}]->(child)
        """,
        parent_name=row['parent_reason_name'],
        child_name=row['reason_name'],
        tree_context=row['tree_context'],
        enabled=bool(row['enabled']))
    print(f"  Done — {len(children)} relationships")

    print("Creating WorkUnit nodes...")
    for _, row in models.iterrows():
        session.run("""
            MERGE (:WorkUnit {name: $model_name})
        """,
        model_name=row["model_name"])

    print(f"  Done — {len(models)} nodes")

    print("Creating USES_REASON_TREE relationships...")

    for _, row in model_reason_links.iterrows():
        session.run("""
            MATCH (m:WorkUnit {name: $model_name})
            MATCH (t:ReasonTree {name: $tree_name})
            MERGE (m)-[:USES_REASON_TREE]->(t)
        """,
        model_name=row["model_name"],
        tree_name=row["reason_tree_name"])

    print(f"  Done — {len(model_reason_links)} relationships")

    # Step 8: HAS_POSSIBLE_REASON relationships
    print("Creating HAS_POSSIBLE_REASON relationships...")
    for _, row in machine_codes.iterrows():
        session.run("""
            MATCH (m:WorkUnit {name: $model_name})
            MATCH (r:Reason {name: $reason_name})
            MERGE (m)-[:HAS_POSSIBLE_REASON {
                codeValue:   $code_value,
                displayName: $display_name,
                description: $description,
                treeContext: $tree_name
            }]->(r)
        """,
        model_name=row['model_name'],
        reason_name=row['reason_name'],
        code_value=row['code_value'],
        display_name=row['display_name'],
        description=row['description'],
        tree_name=row['reason_tree_name'])
    print(f"  Done — {len(machine_codes)} relationships")

    # Step X: Update existing WorkUnit nodes with new properties
    print("Updating WorkUnit node properties...")
    for _, row in workunit_links.iterrows():
        session.run("""
            MATCH (wu:WorkUnit {name: $name})
            SET wu.description  = $description,
                wu.thingName    = $thing_name,
                wu.isPacemaker  = $is_pacemaker
        """,
        name=row['workunit_name'],
        description=row['description'] if pd.notna(row['description']) else None,
        thing_name=row['thing_name'] if pd.notna(row['thing_name']) else None,
        is_pacemaker=bool(row['is_pacemaker']) if pd.notna(row['is_pacemaker']) else False)
    print(f"  Done — {len(workunit_links)} WorkUnit nodes updated")

    # Step X+1: WorkCenter nodes
    print("Creating WorkCenter nodes...")
    for _, row in workcenters.iterrows():
        session.run("""
            MERGE (wc:WorkCenter {name: $name})
            SET wc.description  = $description,
                wc.thingName    = $thing_name,
                wc.targetOEE    = $target_oee
        """,
        name=row['name'],
        description=row['description'] if pd.notna(row['description']) else None,
        thing_name=row['thing_name'] if pd.notna(row['thing_name']) else None,
        target_oee=float(row['target_oee']) if pd.notna(row['target_oee']) else None)
    print(f"  Done — {len(workcenters)} WorkCenter nodes")

# Step X+2: HAS_WORKUNIT relationships (WorkCenter → WorkUnit)
    print("Creating HAS_WORKUNIT relationships...")
    for _, row in workunit_links.iterrows():
        session.run("""
            MATCH (wc:WorkCenter {name: $workcenter_name})
            MATCH (wu:WorkUnit {name: $workunit_name})
            MERGE (wc)-[:HAS_WORKUNIT]->(wu)
        """,
        workcenter_name=row['workcenter_name'],
        workunit_name=row['workunit_name'])
    print(f"  Done — {len(workunit_links)} HAS_WORKUNIT relationships")

    # Area nodes
    print("Creating Area nodes...")
    for _, row in areas.iterrows():
        session.run("""
            MERGE (a:Area {name: $name})
            SET a.description   = $description,
                a.thingName     = $thing_name
        """,
        name=row['name'],
        description=row['description'] if pd.notna(row['description']) else None,
        thing_name=row['thing_name'] if pd.notna(row['thing_name']) else None)
    print(f"  Done — {len(areas)} Area nodes")

    # HAS_WORKCENTER relationships (Area → WorkCenter)
    print("Creating HAS_WORKCENTER relationships...")
    for _, row in workcenter_links.iterrows():
        session.run("""
            MATCH (a:Area {name: $area_name})
            MATCH (wc:WorkCenter {name: $workcenter_name})
            MERGE (a)-[:HAS_WORKCENTER]->(wc)
        """,
        area_name=row['area_name'],
        workcenter_name=row['workcenter_name'])
    print(f"  Done — {len(workcenter_links)} HAS_WORKCENTER relationships")

    # Site nodes
    print("Creating Site nodes...")
    for _, row in sites.iterrows():
        session.run("""
            MERGE (s:Site {name: $name})
            SET s.description   = $description,
                s.thingName     = $thing_name,
                s.targetOEE     = $target_oee,
                s.timeZone      = $time_zone,
                s.regionName    = $region_name
        """,
        name=row['name'],
        description=row['description'] if pd.notna(row['description']) else None,
        thing_name=row['thing_name'] if pd.notna(row['thing_name']) else None,
        target_oee=float(row['target_oee']) if pd.notna(row['target_oee']) else None,
        time_zone=row['time_zone'] if pd.notna(row['time_zone']) else None,
        region_name=row['region_name'] if pd.notna(row['region_name']) else None)
    print(f"  Done — {len(sites)} Site nodes")

    # HAS_AREA relationships (Site → Area)
    print("Creating HAS_AREA relationships...")
    for _, row in area_links.iterrows():
        session.run("""
            MATCH (s:Site {name: $site_name})
            MATCH (a:Area {name: $area_name})
            MERGE (s)-[:HAS_AREA]->(a)
        """,
        site_name=row['site_name'],
        area_name=row['area_name'])
    print(f"  Done — {len(area_links)} HAS_AREA relationships")

    # Enterprise node
    print("Creating Enterprise node...")
    for _, row in enterprises.iterrows():
        session.run("""
            MERGE (e:Enterprise {name: $name})
            SET e.description           = $description,
                e.thingName             = $thing_name,
                e.isDefaultEnterprise   = $is_default
        """,
        name=row['name'],
        description=row['description'] if pd.notna(row['description']) else None,
        thing_name=row['thing_name'] if pd.notna(row['thing_name']) else None,
        is_default=bool(row['is_default_enterprise']) if pd.notna(row['is_default_enterprise']) else False)
    print(f"  Done — {len(enterprises)} Enterprise node")

    # HAS_SITE relationships (Enterprise → Site)
    print("Creating HAS_SITE relationships...")
    for _, row in site_links.iterrows():
        session.run("""
            MATCH (e:Enterprise {name: $enterprise_name})
            MATCH (s:Site {name: $site_name})
            MERGE (e)-[:HAS_SITE]->(s)
        """,
        enterprise_name=row['enterprise_name'],
        site_name=row['site_name'])
    print(f"  Done — {len(site_links)} HAS_SITE relationships")


    print("Creating all WorkUnit nodes...")
    for _, row in all_workunits.iterrows():
        session.run("""
            MERGE (wu:WorkUnit {name: $name})
            SET wu.description  = $description,
                wu.thingName    = $thing_name,
                wu.isPacemaker  = $is_pacemaker
        """,
        name=row['name'],
        description=row['description'] if pd.notna(row['description']) else None,
        thing_name=row['thing_name'] if pd.notna(row['thing_name']) else None,
        is_pacemaker=bool(row['is_pacemaker']) if pd.notna(row['is_pacemaker']) else False)
    print(f"  Done — {len(all_workunits)} WorkUnit nodes")

    # Rerun HAS_WORKUNIT relationships
    for _, row in workunit_links.iterrows():
        session.run("""
            MATCH (wc:WorkCenter {name: $workcenter_name})
            MATCH (wu:WorkUnit {name: $workunit_name})
            MERGE (wc)-[:HAS_WORKUNIT]->(wu)
        """,
        workcenter_name=row['workcenter_name'],
        workunit_name=row['workunit_name'])


neo4j_driver.close()
db_engine.dispose()
print("\nAll done — reason tree loaded into Neo4j")