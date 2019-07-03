from django.db import models


class BaseModel(models.Model):
    """模型抽象基类"""
    create_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    update_time = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    is_delete = models.BooleanField(default=False, verbose_name='删除标记')

    class Meta:
        # 说明是一个抽象模型类
        # 抽象模型类可以为其他表添加抽象模型类所拥有的字段名
        # 如每张表都需要有创建时间,更新时间,是否删除三个字段,因此将这三个字段抽象出来,单独创建一个模型抽象基类,避免在每一张表的模型类中都单独设置这三个字段
        abstract = True
