from dotenv import load_dotenv
from sqlalchemy import create_engine, URL
from pathlib import Path
import pandas as pd
import os

# ================================================
# LOAD .env
# ================================================

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

print("env loaded from:", env_path)
print("PORT:", os.getenv('DPM_PORT'))

# ================================================
# CONNECTION TO DPM Knowledge Graph database
# ================================================

connection_url = URL.create(
    drivername="postgresql+psycopg2",
    username=os.getenv('DPM_USER'),
    password=os.getenv('DPM_PASSWORD'),
    host=os.getenv('DPM_HOST'),
    port=int(os.getenv('DPM_PORT')),
    database=os.getenv('DPM_DB')
)

engine = create_engine(connection_url)

# ================================================
# READ EXCEL SHEETS
# ================================================

excel_path = Path(__file__).parent.parent / "DPM.Sample.1.2.14.xlsx"
xl = pd.ExcelFile(excel_path, engine='openpyxl')

reason_df       = pd.read_excel(xl, sheet_name='Reason')
tree_df         = pd.read_excel(xl, sheet_name='ReasonTree')
node_df         = pd.read_excel(xl, sheet_name='ReasonTreeNode')
model_df        = pd.read_excel(xl, sheet_name='ModelReasonTreeLink')
machinecode_df  = pd.read_excel(xl, sheet_name='MachineCode')
workunit_df     = pd.read_excel(xl, sheet_name='Workunit')
workcenter_df   = pd.read_excel(xl, sheet_name='Workcenter')
area_df         = pd.read_excel(xl, sheet_name='Area')
site_df         = pd.read_excel(xl, sheet_name='Site')
enterprise_df   = pd.read_excel(xl, sheet_name='Enterprise')

node_df = node_df.loc[:, ~node_df.columns.str.contains("^Unnamed")]

# ================================================
# HELPER — Drop selected column
# ================================================

def drop_selected(df):
    """Drop the Selected/selected column — replaced by SERIAL PRIMARY KEY in PostgreSQL."""
    for col in ['Selected', 'selected']:
        if col in df.columns:
            df = df.drop(columns=[col])
    return df

# ================================================
# RENAME COLUMNS TO MATCH TABLE DEFINITIONS
# ================================================

reason_df = reason_df.rename(columns={
    'Name':                 'name',
    'DisplayName':          'display_name',
    'DisplayNameToken':     'display_name_token',
    'Description':          'description',
    'DescriptionToken':     'description_token'
})

tree_df = tree_df.rename(columns={
    'Name':                 'name',
    'Description':          'description',
    'Enable':               'enabled',
    'ReasonCategoryName':   'reason_category_name'
})

node_df = node_df.rename(columns={
    'ParentReasonName':     'parent_reason_name',
    'ReasonName':           'reason_name',
    'ReasonTreeName':       'reason_tree_name',
    'FinalReason':          'final_reason',
    'Enable':               'enabled'
})

model_df = model_df.rename(columns={
    'ModelName':            'model_name',
    'ReasonTreeName':       'reason_tree_name'
})

machinecode_df = machinecode_df.rename(columns={
    'ModelName':            'model_name',
    'ReasonName':           'reason_name',
    'ReasonTreeName':       'reason_tree_name',
    'Name':                 'name',
    'Description':          'description',
    'CodeValue':            'code_value'
})

workunit_df = workunit_df.rename(columns={
    'Name':                         'name',
    'Description':                  'description',
    'ThingName':                    'thing_name',
    'Source':                       'source',
    'IsPacemaker':                  'is_pacemaker',
    'WorkcenterName':               'workcenter_name',
    'BaseTemplate':                 'base_template',
    'ProjectName':                  'project_name',
    'ThingShapes':                  'thing_shapes',
    'IndustrialThing':              'industrial_thing',
    'IndustrialGatewayThingName':   'industrial_gateway_thing_name'
})

workcenter_df = workcenter_df.rename(columns={
    'Name':                     'name',
    'Description':              'description',
    'ThingName':                'thing_name',
    'Source':                   'source',
    'TargetOEE':                'target_oee',
    'ProductionBlockTypeName':  'production_block_type_name',
    'ProductionBlockValue':     'production_block_value',
    'AreaName':                 'area_name',
    'BaseTemplate':             'base_template',
    'ProjectName':              'project_name',
    'ThingShapes':              'thing_shapes'
})

area_df = area_df.rename(columns={
    'Name':         'name',
    'Description':  'description',
    'ThingName':    'thing_name',
    'Source':       'source',
    'SiteName':     'site_name',
    'BaseTemplate': 'base_template',
    'ProjectName':  'project_name',
    'ThingShapes':  'thing_shapes'
})

site_df = site_df.rename(columns={
    'Name':                     'name',
    'Description':              'description',
    'ThingName':                'thing_name',
    'TargetOEE':                'target_oee',
    'ID':                       'site_id',
    'TimeZone':                 'time_zone',
    'WorldClassOEE':            'world_class_oee',
    'OEEOKThreshold':           'oee_ok_threshold',
    'OEEGoodThreshold':         'oee_good_threshold',
    'ProductionBlockTypeName':  'production_block_type_name',
    'ProductionBlockValue':     'production_block_value',
    'BaseTemplate':             'base_template',
    'ProjectName':              'project_name',
    'ThingShapes':              'thing_shapes',
    'RegionName':               'region_name'
})

enterprise_df = enterprise_df.rename(columns={
    'Name':                 'name',
    'Description':          'description',
    'ThingName':            'thing_name',
    'Source':               'source',
    'BaseTemplate':         'base_template',
    'ProjectName':          'project_name',
    'ThingShapes':          'thing_shapes',
    'IsDefaultEnterprise':  'is_default_enterprise'
})

# ================================================
# DROP SELECTED COLUMN FROM ALL DATAFRAMES
# ================================================

reason_df       = drop_selected(reason_df)
tree_df         = drop_selected(tree_df)
node_df         = drop_selected(node_df)
model_df        = drop_selected(model_df)
machinecode_df  = drop_selected(machinecode_df)
workunit_df     = drop_selected(workunit_df)
workcenter_df   = drop_selected(workcenter_df)
area_df         = drop_selected(area_df)
site_df         = drop_selected(site_df)
enterprise_df   = drop_selected(enterprise_df)

# ================================================
# LOAD INTO POSTGRESQL
# NOTE: if_exists='append' preserves the SERIAL PRIMARY KEY
#       created in pgAdmin. Do NOT use 'replace' as it would
#       drop the table and recreate it without the primary key.
# ================================================

with engine.begin() as conn:
    conn.exec_driver_sql("""
        TRUNCATE TABLE
            staging.reason_tree_node,
            staging.machine_code,
            staging.model_reason_tree_link,
            staging.reason_tree,
            staging.reason,
            staging.workunit,
            staging.workcenter,
            staging.area,
            staging.site,
            staging.enterprise
        RESTART IDENTITY CASCADE;
    """)
    
print("Loading reason...")
reason_df.to_sql(
    name='reason',
    schema='staging',
    con=engine,
    if_exists='append',
    index=False
)
print(f"  {len(reason_df)} rows loaded")

print("Loading reason_tree...")
tree_df.to_sql(
    name='reason_tree',
    schema='staging',
    con=engine,
    if_exists='append',
    index=False
)
print(f"  {len(tree_df)} rows loaded")

print("Loading reason_tree_node...")
node_df.to_sql(
    name='reason_tree_node',
    schema='staging',
    con=engine,
    if_exists='append',
    index=False
)
print(f"  {len(node_df)} rows loaded")

print("Loading model_reason_tree_link...")
model_df.to_sql(
    name='model_reason_tree_link',
    schema='staging',
    con=engine,
    if_exists='append',
    index=False
)
print(f"  {len(model_df)} rows loaded")

print("Loading machine_code...")
machinecode_df.to_sql(
    name='machine_code',
    schema='staging',
    con=engine,
    if_exists='append',
    index=False
)
print(f"  {len(machinecode_df)} rows loaded")

print("Loading workunit...")
workunit_df.to_sql(
    name='workunit',
    schema='staging',
    con=engine,
    if_exists='append',
    index=False
)
print(f"  {len(workunit_df)} rows loaded")

print("Loading workcenter...")
workcenter_df.to_sql(
    name='workcenter',
    schema='staging',
    con=engine,
    if_exists='append',
    index=False
)
print(f"  {len(workcenter_df)} rows loaded")

print("Loading area...")
area_df.to_sql(
    name='area',
    schema='staging',
    con=engine,
    if_exists='append',
    index=False
)
print(f"  {len(area_df)} rows loaded")

print("Loading site...")
site_df.to_sql(
    name='site',
    schema='staging',
    con=engine,
    if_exists='append',
    index=False
)
print(f"  {len(site_df)} rows loaded")

print("Loading enterprise...")
enterprise_df.to_sql(
    name='enterprise',
    schema='staging',
    con=engine,
    if_exists='append',
    index=False
)
print(f"  {len(enterprise_df)} rows loaded")

print("\nAll data loaded into PostgreSQL successfully")