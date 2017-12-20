from datetime import datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from transcriber.database import db
from transcriber.models import FormMeta, FormSection, TaskGroup, FormField, Image
from transcriber.app_config import TIME_ZONE
from transcriber.helpers import slugify

SQL_DATA_TYPE = {
    'boolean': 'BOOLEAN',
    'string': 'VARCHAR',
    'integer': 'INTEGER',
    'datetime': 'TIMESTAMP WITH TIME ZONE',
    'date': 'DATE'
}

DATA_TYPE = {
    'boolean': sa.Boolean,
    'string': sa.String,
    'integer': sa.Integer,
    'datetime': sa.DateTime,
    'date': sa.Date
}

class FormCreatorManager(object):
    def __init__(self,
                 form_id=None,
                 election_name=None,
                 hierarchy_filter=None):

        self.form_meta = FormMeta()
        self.existing_form = False
        self.section_mapping = []
        self.next_section_index = 2
        self.next_field_indices = {1: 2}

        self.election_name = election_name
        self.hierarchy_filter = hierarchy_filter

        if form_id:
            self.form_meta = db.session.query(FormMeta).get(form_id)
            self.existing_form = True
            self.election_name = self.form_meta.election_name
            self.hierarchy_filter = self.form_meta.hierarchy_filter

        else:
            padded_filters = []

            if self.hierarchy_filter:

                max_length_filter = max(len(f) for f in self.hierarchy_filter)

                for filter in hierarchy_filter:
                    if len(filter) < max_length_filter:
                        filter += [None for i in range(max_length_filter - len(filter))]

                    padded_filters.append(filter)

            self.hierarchy_filter = padded_filters
            existing = db.session.query(FormMeta)\
                                 .filter(FormMeta.election_name == self.election_name)\
                                 .filter(FormMeta.hierarchy_filter == self.hierarchy_filter).first()

            if existing:
                self.form_meta = existing
                self.existing_form = True
            else:
                self.form_meta.election_name = self.election_name
                self.form_meta.hierarchy_filter = self.hierarchy_filter
                sample_image = Image.grab_sample_image(self.election_name,
                                                    hierarchy_filter=self.hierarchy_filter)
                self.form_meta.sample_image = sample_image

                db.session.add(self.form_meta)
                db.session.commit()

        db.session.refresh(self.form_meta)

    def getNextIndices(self):

        engine = db.session.bind

        sel = '''
            SELECT
                s.index + 1 as section_index
            FROM form_meta as m
            JOIN form_section as s
                ON m.id = s.form_id
            WHERE m.id = :form_id
            ORDER BY section_index DESC
            LIMIT 1
        '''

        row = engine.execute(sa.text(sel),
                             form_id=self.form_meta.id).first()

        if row:
            self.next_section_index = cursor.first().section_index

            sel = '''
                SELECT
                    s.index as section_index,
                    MAX(f.index) AS field_index
                FROM form_meta as m
                JOIN form_section as s
                    ON m.id = s.form_id
                JOIN form_field as f
                    ON s.id = f.section_id
                WHERE m.id = :form_id
                GROUP BY s.id
            '''
            self.next_field_indices = {f.section_index: f.field_index for f in \
                                            engine.execute(sa.text(sel), form_id=self.form_meta.id)}

    def updateFormMeta(self, post_data, sample_image=None):

        self.post_data = post_data

        if post_data.get('task_group_id'):
            task_group = db.session.query(TaskGroup)\
                           .get(self.post_data['task_group_id'])
            task_group.name = self.post_data['task_group']
        else:
            task_group = TaskGroup(name=self.post_data['task_group'],
                                   description=self.post_data.get('task_group_description'))

        split_image = True
        if self.post_data.get('is_concat', 'keep_intact') == 'keep_intact':
            split_image = False

        self.form_meta.name = post_data['task_name']
        self.form_meta.description = post_data['task_description']
        self.form_meta.slug = slugify(post_data['task_name'])
        self.form_meta.last_update = datetime.now().replace(tzinfo=TIME_ZONE)
        self.form_meta.task_group = task_group
        self.form_meta.deadline = post_data['deadline']
        self.form_meta.reviewer_count = post_data['reviewer_count']
        self.form_meta.split_image = split_image
        self.form_meta.election_name = self.election_name
        self.form_meta.hierarchy_filter = self.hierarchy_filter
        self.form_meta.sample_image = sample_image

        db.session.add(task_group)
        db.session.add(self.form_meta)
        db.session.commit()

    def extractFormInfo(self):
        section_info = []
        field_info = []
        datatype_info = []

        sections = {}

        for field_name, field_value in self.post_data.items():
            parts = [part for part in field_name.split('_') if 'section' in field_name]

            if len(parts) == 2:
                section_info.append(([int(parts[1]),], field_value,))

            if len(parts) == 4:
                field_info.append(([int(parts[1]), int(parts[3]),], field_value,))

            if len(parts) == 5:
                datatype_info.append(([int(parts[2]), int(parts[4]),], field_value,))

        section_info = sorted(section_info,
                              key=lambda x: x[0][0])

        for indices, field_value in section_info:

            sections[indices[0]] = {
                'name': field_value,
                'index': indices[0],
                'fields': {},
            }

        field_info = sorted(field_info,
                            key=lambda x: (x[0][0], x[0][1],))

        # TODO: Do we need a better way of setting default datatype for field?
        for indices, field_value in field_info:
            section_index, field_index = indices

            field_info = {
                'name': field_value,
                'index': field_index,
                'data_type': None
            }

            sections[section_index]['fields'][field_index] = field_info

        datatype_info = sorted(datatype_info,
                               key=lambda x: (x[0][0], x[0][1],))

        for indices, field_value in datatype_info:
            section_index, field_index = indices

            sections[section_index]['fields'][field_index]['data_type'] = field_value

        return sections

    def saveFormParts(self):

        sections = self.extractFormInfo()

        for section_info in sections.values():

            section = self.getOrCreateSection(section_info['index'],
                                              section_info['name'])

            for field_info in section_info['fields'].values():

                field = self.getOrCreateField(field_info['index'],
                                              field_info['name'],
                                              field_info['data_type'],
                                              section)

        if not self.existing_form:
            self.createDataTable()

        db.session.commit()
        db.session.refresh(self.form_meta, ['fields', 'table_name'])

        self.addNewFields()

    def getOrCreateSection(self, section_index, section_name):

        section = db.session.query(FormSection)\
                    .filter(FormSection.index == section_index)\
                    .filter(FormSection.form == self.form_meta)\
                    .first()

        if not section:
            section = FormSection(name=section_name,
                                  slug=slugify(section_name),
                                  index=section_index,
                                  form=self.form_meta)
        else:
            section.name = section_name
            section.slug = slugify(section_name)

        db.session.add(section)
        db.session.commit()

        return section

    def getOrCreateField(self,
                         field_index,
                         field_name,
                         field_data_type,
                         section):

        field = db.session.query(FormField)\
                .filter(FormField.index == field_index)\
                .filter(FormField.section_id == section.id)\
                .filter(FormField.form_id == self.form_meta.id)\
                .first()

        if not field:

            field = FormField(name=field_name,
                              slug=slugify(field_name, truncate=True),
                              index=field_index,
                              form=self.form_meta,
                              section=section,
                              data_type=field_data_type)

        if field.slug != slugify(field_name, truncate=True):
            self.alterFieldName(field.slug, slugify(field_name, truncate=True))
            field.slug = slugify(field_name, truncate=True)

        if field.name != field_name:
            field.name = field_name

        db.session.add(field)
        db.session.commit()

        return field

    def createDataTable(self):

        table_name = '{0}_{1}'.format(
                str(uuid4()).rsplit('-', 1)[1],
                self.form_meta.slug)[:60]

        cols = [
            sa.Column('date_added', sa.DateTime(timezone=True),
                server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('transcriber', sa.String),
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('image_id', UUID),
            sa.Column('transcription_status', sa.String, default="raw"),
            sa.Column('flag_irrelevant', sa.Boolean)
        ]

        for field in self.form_meta.fields:
            dt = DATA_TYPE.get(field.data_type, sa.String)
            if field.data_type  == 'datetime':
                dt = sa.DateTime(timezone=True)
            cols.append(sa.Column(field.slug, dt))

            cols.append(sa.Column('{0}_blank'.format(field.slug),
                                  sa.Boolean,
                                  server_default=sa.text('FALSE')))

            cols.append(sa.Column('{0}_not_legible'.format(field.slug),
                                  sa.Boolean,
                                  server_default=sa.text('FALSE')))

            cols.append(sa.Column('{0}_altered'.format(field.slug),
                                  sa.Boolean,
                                  server_default=sa.text('FALSE')))

        table = sa.Table(table_name, sa.MetaData(), *cols)

        engine = db.session.bind
        table.create(bind=engine)

        self.form_meta.table_name = table_name
        db.session.add(self.form_meta)
        db.session.commit()

    def alterFieldName(self, old_name, new_name):

        fmt_args = [self.form_meta.table_name, old_name, new_name,]

        rename = '''
            ALTER TABLE "{0}"
            RENAME COLUMN "{1}" TO "{2}"
        '''.format(*fmt_args)

        rename_blank = '''
            ALTER TABLE "{0}"
            RENAME COLUMN "{1}_blank" TO "{2}_blank"
        '''.format(*fmt_args)

        rename_not_legible = '''
            ALTER TABLE "{0}"
            RENAME COLUMN "{1}_not_legible" TO "{2}_not_legible"
        '''.format(*fmt_args)

        rename_altered = '''
            ALTER TABLE "{0}"
            RENAME COLUMN "{1}_altered" TO "{2}_altered"
        '''.format(*fmt_args)

        engine = db.session.bind

        with engine.begin() as conn:
            conn.execute(rename)
            conn.execute(rename_blank)
            conn.execute(rename_not_legible)
            conn.execute(rename_altered)

    def addNewFields(self):

        engine = db.session.bind

        table = sa.Table(self.form_meta.table_name, sa.MetaData(),
                         autoload=True, autoload_with=engine)

        new_columns = set([f.slug for f in self.form_meta.fields])
        existing_columns = set([c.name for c in table.columns])
        additional_columns = new_columns - existing_columns

        for column in additional_columns:


            field = [f for f in self.form_meta.fields if f.slug == str(column)][0]
            sql_type = SQL_DATA_TYPE[field.data_type]

            fmt_args = [self.form_meta.table_name, field.slug, sql_type,]

            alt = 'ALTER TABLE "{0}" ADD COLUMN "{1}" {2}'\
                    .format(*fmt_args)

            blank = '''
                ALTER TABLE "{0}"
                ADD COLUMN "{1}_blank" boolean
                '''.format(*fmt_args)

            not_legible = '''
                ALTER TABLE "{0}"
                ADD COLUMN "{1}_not_legible" boolean
                '''.format(*fmt_args)

            altered = '''
                ALTER TABLE "{0}"
                ADD COLUMN "{1}_altered" boolean
                '''.format(*fmt_args)

            with engine.begin() as conn:
                conn.execute(alt)
                conn.execute(blank)
                conn.execute(not_legible)
                conn.execute(altered)
