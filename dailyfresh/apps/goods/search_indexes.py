from goods.models import GoodsSKU
from haystack import indexes


class GoodsSKUIndex(indexes.SearchIndex, indexes.Indexable):
    """商品索引类"""
    # 将根据关键字生成的索引,生成一张表,
    # use_temlate 根据关键字字段设置索引的说明放在一个文件中,即 template/search/indexes/goods/godssku_text.txt 文件
    text = indexes.CharField(document=True, use_template=True)

    def get_model(self):
        return GoodsSKU

    def index_queryset(self, using=None):
        return self.get_model().objects.all()