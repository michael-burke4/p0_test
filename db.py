import peewee

import config


db = peewee.SqliteDatabase(f'{config.DBFILE}')


class Level(peewee.Model):
    name = peewee.TextField(primary_key=True)

    class Meta:
        database = db


class Test(peewee.Model):
    level = peewee.ForeignKeyField(Level, backref='tests')
    test_text = peewee.TextField(unique=True)

    class Meta:
        database = db
