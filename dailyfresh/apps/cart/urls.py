from django.conf.urls import url
from cart.views import AddCartView, CartInfoView, UpdateCartView, DeleteCartView


urlpatterns = [
    url(r'^add$', AddCartView.as_view(), name='add'),  # 购物车添加
    url(r'^$', CartInfoView.as_view(), name='info'),  # 购物车页面
    url(r'^update$', UpdateCartView.as_view(), name='update'),  # 购物车页面更新
    url(r'^delete$', DeleteCartView.as_view(), name='delete'),  # 删除购物车
]
