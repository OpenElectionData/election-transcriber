import csv
import os

import sqlalchemy as sa

from transcriber.app_config import DB_CONN

engine = sa.create_engine(DB_CONN)

this_dir = os.path.abspath(os.path.dirname(__file__))

counties = set()
constituencies = set()
caws = set()
registration_centers = set()
polling_centers = set()

with open(os.path.join(this_dir, 'psdata.csv')) as f:
    reader = csv.reader(f)

    header = next(reader)

    for row in reader:
        counties.add(tuple(row[:2]))
        constituencies.add(tuple(row[2:4]))
        caws.add(tuple(row[4:6]))

        reg_center_code, reg_center_name = row[6:8]
        try:
            reg_voters = int(row[8])
        except ValueError:
            reg_voters = None

        registration_centers.add((reg_center_code,
                                  reg_center_name,
                                  reg_voters,))

        poll_center_code, poll_center_name = row[9:11]
        try:
            poll_voters = int(row[11])
        except ValueError:
            poll_voters = None

        
        polling_centers.add((poll_center_code,
                             poll_center_name,
                             poll_voters,))

insert = '''
    INSERT INTO project_geography (
      project,
      geo_type,
      code,
      name
    ) VALUES (
      'Kenya rerun -- TEST',
      '{}',
      :code,
      :name
    )
'''

with engine.begin() as conn:
    counties = [dict(zip(['code', 'name'], c)) for c in counties]
    conn.execute(sa.text(insert.format('county')), *counties)

with engine.begin() as conn:
    constituencies = [dict(zip(['code', 'name'], c)) for c in constituencies]
    conn.execute(sa.text(insert.format('consituency')), *constituencies)

with engine.begin() as conn:
    caws = [dict(zip(['code', 'name'], c)) for c in caws]
    conn.execute(sa.text(insert.format('caw')), *caws)

insert = '''
    INSERT INTO project_geography (
      project,
      geo_type,
      code,
      name,
      voter_count
    ) VALUES (
      'Kenya rerun -- TEST',
      '{}',
      :code,
      :name,
      :voter_count
    )
'''

with engine.begin() as conn:
    registration_centers = [dict(zip(['code', 'name', 'voter_count'], c)) for c in registration_centers]
    conn.execute(sa.text(insert.format('registration center')), *registration_centers)

with engine.begin() as conn:
    polling_centers = [dict(zip(['code', 'name', 'voter_count'], c)) for c in polling_centers]
    conn.execute(sa.text(insert.format('polling place')), *polling_centers)
