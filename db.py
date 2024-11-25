import peewee

import config


db = peewee.SqliteDatabase(f'{config.DBFILE}')


class Level(peewee.Model):
    name = peewee.TextField(primary_key=True)

    class Meta:
        database = db


class Test(peewee.Model):
    level = peewee.ForeignKeyField(Level, backref='tests', null=False)
    test_text = peewee.TextField(null=False)

    class Meta:
        database = db


class Submitter(peewee.Model):
    name = peewee.TextField(primary_key=True)
    known_good = peewee.CharField(null=False,
                                  choices=[('t', 'True'), ('f', 'False')])

    class Meta:
        database = db


class Result(peewee.Model):
    submitter = peewee.ForeignKeyField(Submitter, backref='results',
                                       null=False)
    level = peewee.ForeignKeyField(Level, backref='results', null=False)
    test = peewee.ForeignKeyField(Test, backref='results', null=False)
    stdout = peewee.TextField(null=True)
    stderr = peewee.TextField(null=True)
    timedout = peewee.CharField(choices=[('t', 'True'), ('f', 'False')],
                                null=True)
    exit_code = peewee.IntegerField(null=True)
    good_match = peewee.ForeignKeyField('self', null=True, backref='matches')

    okness = peewee.CharField(choices=[('ok', 'OK'),
                                       ('not_ok', 'Not OK'),
                                       ],
                              null=True)

    class Meta:
        database = db
