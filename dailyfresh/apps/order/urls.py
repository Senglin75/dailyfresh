from django.conf.urls import url
from order.views import OrderPlaceView, OrderCommitView, OrderPayView, OrderCheckView, OrderCommentView

urlpatterns = [
    url(r'^place$', OrderPlaceView.as_view(), name='place'),  # 订单显示页面
    url(r'^commit$', OrderCommitView.as_view(), name='commit'),  # 订单提交页面
    url(r'^pay$', OrderPayView.as_view(), name='pay'),  # 订单支付界面
    url(r'^check$', OrderCheckView.as_view(), name='check'),  # 支付确认
    url(r'^comment/(?P<order_id>.+)$', OrderCommentView.as_view(), name='comment'),  # 订单评论页

]