import unittest

from sqlalchemy import Integer, Unicode
from nanohttp import settings

from restfulpy.testing import WebAppTestCase
from restfulpy.tests.helpers import MockupApplication
from restfulpy.orm import DeclarativeBase, Field, DBSession, ActivationMixin


class ActiveObject(ActivationMixin, DeclarativeBase):
    __tablename__ = 'active_object'

    id = Field(Integer, primary_key=True)
    title = Field(Unicode(50), index=True, min_length=2, watermark='First Name')


class ActivationMixinTestCase(WebAppTestCase):
    application = MockupApplication('MockupApplication', None)
    __configuration__ = '''
    db:
      uri: sqlite://    # In memory DB
      echo: false
    '''

    @classmethod
    def configure_app(cls):
        cls.application.configure(force=True)
        settings.merge(cls.__configuration__)

    def test_activation_mixin(self):
        # noinspection PyArgumentList
        object1 = ActiveObject(
            title='object 1',
        )

        DBSession.add(object1)
        DBSession.commit()
        self.assertFalse(object1.is_active)
        self.assertEquals(DBSession.query(ActiveObject).filter(ActiveObject.is_active).count(), 0)

        object1.is_active = True
        self.assertTrue(object1.is_active)
        DBSession.commit()
        object1 = DBSession.query(ActiveObject).one()
        self.assertTrue(object1.is_active)

        json = object1.to_dict()
        self.assertIn('isActive', json)

        self.assertEquals(DBSession.query(ActiveObject).filter(ActiveObject.is_active).count(), 1)
        self.assertEquals(ActiveObject.filter_activated().count(), 1)

        self.assertFalse(ActiveObject.import_value(ActiveObject.is_active, 'false'))
        self.assertFalse(ActiveObject.import_value(ActiveObject.is_active, 'FALSE'))
        self.assertFalse(ActiveObject.import_value(ActiveObject.is_active, 'False'))
        self.assertTrue(ActiveObject.import_value(ActiveObject.is_active, 'true'))
        self.assertTrue(ActiveObject.import_value(ActiveObject.is_active, 'TRUE'))
        self.assertTrue(ActiveObject.import_value(ActiveObject.is_active, 'True'))


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
