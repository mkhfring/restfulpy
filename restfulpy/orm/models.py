
import cgi
from datetime import datetime, date, time
from decimal import Decimal

from nanohttp import HttpBadRequest
from sqlalchemy import Column, event
from sqlalchemy.orm import SynonymProperty, validates
from sqlalchemy.inspection import inspect
from sqlalchemy.orm.relationships import RelationshipProperty

from restfulpy.utils import format_iso_datetime, format_iso_time
from restfulpy.orm.metadata import MetadataField
from restfulpy.orm.field import Field


class BaseModel(object):
    _key_serializer = None

    @classmethod
    def get_column(cls, column):
        if isinstance(column, str):
            mapper = inspect(cls)
            return mapper.columns[column]
        if isinstance(column, SynonymProperty):
            return column.parent.columns[column.name]
        return column

    @classmethod
    def convert_value(cls, column, v):
        c = cls.get_column(column)
        if isinstance(c, Column):
            if c.type.python_type is bool and not isinstance(v, bool):
                return str(v).lower() == 'true'
        return v

    @classmethod
    def prepare_for_export(cls, column, v):
        param_name = column.info.get('json') or column.key

        if isinstance(column, RelationshipProperty) and column.uselist:
            result = [c.to_dict() for c in v]

        elif isinstance(v, datetime):
            result = format_iso_datetime(v)

        elif isinstance(v, date):
            result = v.isoformat()

        elif isinstance(v, time):
            result = format_iso_time(v)

        elif v is None:
            result = v

        elif hasattr(v, 'to_dict'):
            result = v.to_json()

        elif isinstance(v, Decimal):
            result = str(v)

        elif isinstance(v, set):
            result = list(v)

        else:
            result = v

        return param_name, result

    @classmethod
    def from_request(cls, request):
        model = cls()
        # noinspection PyUnresolvedReferences
        DBSession.add(model)
        model.update_from_request(request)
        return model

    @classmethod
    def json_metadata(cls):
        fields = {}
        for c in cls.iter_json_columns(relationships=True, include_readonly_columns=True):
            metadata_fields = MetadataField.from_column(cls.get_column(c), info=c.info)
            for f in metadata_fields:
                fields[f.key] = f
        return fields

    def update_from_request(self, request):
        for column, value in self.extract_data_from_request(request):
            if isinstance(column, Field) and column.is_attachment:
                if value is not None and (isinstance(value, cgi.FieldStorage) or hasattr(value, 'read')):
                    getattr(self, column.key[1:]).from_request(request, column, value)
            else:
                if 'unreadable' in column.info and (not value or (isinstance(value, str) and not value.strip())):
                    continue
                setattr(
                    self,
                    column.key[1:] if column.key.startswith('_') else column.key,
                    self.convert_value(column, value))

    @classmethod
    def iter_columns(cls, relationships=True, synonyms=True, use_inspection=True):
        if use_inspection:
            mapper = inspect(cls)
            for c in mapper.columns:
                yield c

            if synonyms:
                for c in mapper.synonyms:
                    yield c

            if relationships:
                for c in mapper.relationships:
                    yield c
        else:
            # noinspection PyUnresolvedReferences
            for c in cls.__table__.c:
                yield c

    @classmethod
    def iter_json_columns(cls, include_readonly_columns=True, **kw):
        for c in cls.iter_columns(**kw):
            if c.info.get('protected') or \
                    (not include_readonly_columns and c.info.get('readonly')):
                continue

            yield c

    @classmethod
    def extract_data_from_request(cls, request):
        for c in cls.iter_json_columns():
            param_name = c.info['json']

            if 'readonly' in c.info and c.info['readonly'] and \
                    (param_name in request.form_dict or (request.files and param_name in request.files)):
                raise HttpBadRequest('Invalid parameter: %s' % c.info['json'])

            if param_name in request.form_dict:
                yield c, request.form_dict[param_name]
            elif request.files and param_name in request.files:
                yield c, request.files[param_name][0]

    def to_dict(self):
        result = {}
        for c in self.iter_json_columns():
            result.setdefault(*self.prepare_for_export(c, getattr(self, c.key)))
        return result


@event.listens_for(BaseModel, 'class_instrument')
def receive_class_instrument(cls):
    for field in cls.iter_columns(relationships=False, synonyms=False, use_inspection=False):
        if not isinstance(field, Field) or not field.can_validate:
            continue
        method_name = 'validate_%s' % field.name
        if not hasattr(cls, method_name):
            def validator(self, key, value):
                return self.get_column(key).validate(value)

            setattr(cls, method_name, validates(field.name)(validator))