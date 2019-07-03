from django.db import models
from db.base_model import BaseModel
from tinymce.models import HTMLField


class GoodsType(BaseModel):
    """商品类型模型类"""
    name = models.CharField(max_length=20, verbose_name="商品名称")
    logo = models.CharField(max_length=20, verbose_name="标识")
    # uoLoad_to: django 默认会将图片上传到你所指定的文件夹,但由于此操作耗时太长,因此选用 redis 来处理这部分,所以这里的上传位置 'images' 只是一个占位符,并不具有实际意义
    image = models.ImageField(upload_to='image', verbose_name="商品类型图片")

    class Meta:
        # 指定该模型类所对应的表
        db_table = 'df_goods_type'
        verbose_name = '商品种类'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class GoodsSKU(BaseModel):
    """商品 SKU 模型类"""
    status_choices = (
        (0, '上线'),
        (1, '下线')
    )
    type = models.ForeignKey('GoodsType', verbose_name='商品种类')
    goods = models.ForeignKey('Goods', verbose_name='商品SPU')
    name = models.CharField(max_length=20, verbose_name='商品名称')
    desc = models.CharField(max_length=256, verbose_name='商品简介')
    price = models.DecimalField(max_digits=10, default=0, decimal_places=2, verbose_name='商品价格')
    unite = models.CharField(max_length=20, verbose_name='商品单位')
    image = models.ImageField(upload_to='image', verbose_name='商品图片')

    stock = models.IntegerField(default=1, verbose_name='商品库存')
    sales = models.IntegerField(default=0, verbose_name='商品销量')
    status = models.SmallIntegerField(default=1, choices=status_choices, verbose_name='商品状态')

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'df_goods_sku'
        verbose_name = '商品'
        verbose_name_plural = verbose_name


class Goods(BaseModel):
    """商品 SPU 模型类"""
    name = models.CharField(max_length=20, verbose_name='商品SPU名称')
    # 富文本类型: 带样式的文本
    detail = HTMLField(blank=True, verbose_name='商品详情')

    class Meta:
        db_table = 'df_goods'
        verbose_name = '商品SPU'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class GoodsImage(BaseModel):
    """商品图片模型类"""
    sku = models.ForeignKey('GoodsSKU', verbose_name='商品图片')
    image = models.ImageField(upload_to='image', verbose_name='图片路径')

    class Meta:
        db_table = 'df_goods_image'
        verbose_name = '商品图片'
        verbose_name_plural = verbose_name


class IndexGoodsBanner(BaseModel):
    """首页商品轮播展示模型类"""
    sku = models.ForeignKey('GoodsSKU', verbose_name='商品')
    image = models.ImageField(upload_to='image', verbose_name='图片')
    index = models.SmallIntegerField(default=0, verbose_name='展示顺序')

    class Meta:
        db_table = 'df_index_banner'
        verbose_name = '首页轮播商品'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.sku.type.name


class IndexTypeGoodsBanner(BaseModel):
    """首页分类商品展示模型类"""
    display_type_choices = (
        (0, '标题'),
        (1, '图片')
    )

    type = models.ForeignKey('GoodsType', verbose_name='商品类型')
    sku = models.ForeignKey('GoodsSKU', verbose_name='商品SKU')
    display_type = models.SmallIntegerField(default=1, choices=display_type_choices, verbose_name='展示商品类型')
    index = models.SmallIntegerField(default=0, verbose_name='展示顺序')

    class Meta:
        db_table = 'df_index_type_goods'
        verbose_name = '首页分类展示商品'
        verbose_name_plural = verbose_name

    def __str__(self):
        if self.display_type == 0:
            return  '%s_%s_%s' % (self.type.name, self.sku.name, '标题')
        else:
            return '%s_%s_%s' % (self.type.name, self.sku.name, '图片')


class IndexPromotionBanner(BaseModel):
    """首页促销模型类"""
    name = models.CharField(max_length=20, verbose_name='活动名称')
    url = models.CharField(max_length=20, verbose_name='活动连接')
    image = models.ImageField(upload_to='image', verbose_name='活动图片')
    index = models.SmallIntegerField(default=0, verbose_name='展示顺序')

    class Meta:
        db_table = 'df_index_promotion'
        verbose_name = '首页促销活动'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


