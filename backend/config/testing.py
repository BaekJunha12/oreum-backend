"""테스트 도우미.

ERD(docs/db/erd.sql)의 CREATE TABLE 을 읽어서, 모델이 ERD 의 칸을 빠짐없이 갖고 있는지 확인해요.
모델에만 있는 칸(Django 가 필요로 하는 것)은 docs/db/README.md 에 적고 extra 로 넘겨요.
"""
import re

from django.conf import settings

ERD_PATH = settings.BASE_DIR.parent / 'docs' / 'db' / 'erd.sql'


def erd_tables():
    """{ 테이블 이름: {칸 이름, ...} }"""
    sql = ERD_PATH.read_text(encoding='utf-8')
    tables = {}
    for name, body in re.findall(r'CREATE TABLE `(\w+)` \((.*?)\n\) ENGINE', sql, re.S):
        tables[name] = set(re.findall(r'^\s*`(\w+)`\s', body, re.M))
    return tables


def model_columns(model):
    return {f.column for f in model._meta.concrete_fields if f.column}


class ErdContractMixin:
    """class Tests(ErdContractMixin, TestCase): models = [(Model, {'모델에만 있는 칸'}), ...]"""

    models = []

    def test_models_match_erd(self):
        tables = erd_tables()
        for model, extra in self.models:
            with self.subTest(table=model._meta.db_table):
                self.assertIn(model._meta.db_table, tables, 'ERD 에 없는 테이블')
                self.assertEqual(model_columns(model), tables[model._meta.db_table] | set(extra))
