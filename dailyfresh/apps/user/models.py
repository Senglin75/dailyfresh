from django.db import models
# django 预留的管理员模型类
from django.contrib.auth.models import AbstractUser
from db.base_model import BaseModel


class User(AbstractUser, BaseModel):
    """用户模型类"""
    class Meta:
        db_table = 'df_user'
        verbose_name = '用户'
        verbose_name_plural = verbose_name


class AddressManger(models.Manager):
    """创建一个 Address 管理类"""
    def get_default_address(self, user):
        try:
            address = self.get(user=user, is_default=True)
        except self.model.DoesNotExist as e:
            address = None

        return address


class Address(BaseModel):
    """地址模型类"""
    user = models.ForeignKey('User', verbose_name='所属账户')
    receiver = models.CharField(max_length=20, verbose_name='收件人')
    add = models.CharField(max_length=20, verbose_name='收件地址')
    zip_code = models.CharField(max_length=6, null=True, verbose_name='邮政编码')
    phone = models.CharField(max_length=11, verbose_name='电话号码')
    is_default = models.BooleanField(default=False, verbose_name='是否默认')

    objects = AddressManger()

    class Meta:
        db_table = 'df_address'
        verbose_name = '收件地址'
        verbose_name_plural = verbose_name
