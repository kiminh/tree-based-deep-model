import os
import time
import random
import multiprocessing as mp
import pandas as pd
import numpy as np
from .construct_tree import TreeInitialize
import pickle
from ximalaya_brain_utils.hdfs_util import HdfsClient
#载入csv处理写入pickle
import glob,os

def _mask_padding(data, max_len):
    size = data.shape[0]
    raw = data.values
    mask = np.array([[-2] * max_len for _ in range(size)])
    for i in range(size):
        mask[i, :len(raw[i])] = raw[i]
    return mask.tolist()


def data_process(local):
    """convert and split the raw data."""
    #user_id,item_id,category_id,behavior_type index化
    path = local
    print(path)
    file = glob.glob(os.path.join(path, "*.csv"))
    dl = []
    for f in file:
        dl.append(pd.read_csv(f, header=None,
                           names=['user_ID', 'item_ID', 'category_ID']))
    data_raw = pd.concat(dl).dropna().reset_index(drop=True)
    print(data_raw)
    #去除一部分数据跑跑看
    data_raw = data_raw.iloc[0:30000000,:]
    # print('finish load')
    # print(data_raw)
    user_list = data_raw.user_ID.drop_duplicates().to_list()
    user_dict = dict(zip(user_list, range(len(user_list))))
    data_raw['user_ID'] = data_raw.user_ID.apply(lambda x: user_dict[x])
    item_list = data_raw.item_ID.drop_duplicates().to_list()
    item_dict = dict(zip(item_list, range(len(item_list))))
    data_raw['item_ID'] = data_raw.item_ID.apply(lambda x: item_dict[x])
    category_list = data_raw.category_ID.drop_duplicates().to_list()
    category_dict = dict(zip(category_list, range(len(category_list))))
    data_raw['category_ID'] = data_raw.category_ID.apply(lambda x: category_dict[x])

    print('start build tree')
    #建立二叉树
    random_tree = TreeInitialize(data_raw)
    _ = random_tree.random_binary_tree()
    print('stop build tree')

    #行为数据按user_id,timestamp聚合
    data = data_raw.groupby(['user_ID'])['item_ID'].apply(list).reset_index()
    data['behavior_num'] = data.item_ID.apply(lambda x: len(x))
    print('computer behavior_num')
    #过滤行为数据小于10次的user
    # mask_length = data.behavior_num.max()
    # data = data[data.behavior_num >= 2]
    # data = data[data.behavior_num < 10]
    # print('finish filter num > 10')
    #加mask
    # data['item_ID'] = _mask_padding(data['item_ID'], mask_length)
    #data 'user_ID',timestamp 'item_list', 'behaviors_list'
    data_train, data_validate = data[:-200000], data[-200000:]
    cache = (user_dict, item_dict, random_tree)
    # return data_train, data_validate.reset_index(drop=True), cache
    with open('/home/dev/data/andrew.zhu/tdm/data_flow/sample.pkl', 'wb') as f:
        pickle.dump(data_train, f, pickle.HIGHEST_PROTOCOL) # uid, iid
        pickle.dump(data_validate, f, pickle.HIGHEST_PROTOCOL) # cid of iid line
        pickle.dump(cache,
                    f, pickle.HIGHEST_PROTOCOL)

def test_pickle():
    with open('/home/dev/data/andrew.zhu/tdm/data_flow/sample.pkl', 'rb') as f:
        data_train = pickle.load(f)
        data_validate = pickle.load(f)
        user_dict, item_dict, random_tree = pickle.load(f)
        print('data_train %d' % len(data_train))
        print('data_validate %d' % len(data_validate))
        print('user_num %d'% len(user_dict))
        print('item_num %d' % len(item_dict))
        print('tree_item_num %d' % len(random_tree.items))
        print('tree_node_num %d' % random_tree.node_size)
        # print(user_dict)
        # print(item_dict)
        # print(random_tree)

def _single_node_sample(item_id, node, root):
    samples = []
    positive_info = {}
    i = 0
    s = time.clock()
    while node:
        if node.item_id is None:
            single_sample = [item_id, node.val, 0, 1]
        else:
            single_sample = [item_id, node.item_id, 1, 1]
        samples.append(single_sample)
        positive_info[i] = node
        node = node.parent
        i += 1
    #j代表 叶子节点到root一路的index k代表当前level
    j, k = i-1, 0
    level_nodes = [root]
    while level_nodes:
        tmp = []
        for node in level_nodes:
            if node.left:
                tmp.append(node.left)
            if node.right:
                tmp.append(node.right)
        if j >= 0:
            level_nodes.remove(positive_info[j])
        if level_nodes:
            if len(level_nodes) <= 2*k:
                index_list = range(len(level_nodes))
            else:
                index_list = random.sample(range(len(level_nodes)), 2*k)
            if j == 0:
                index_list = random.sample(range(len(level_nodes)), 80)
            for level_index in index_list:
                if level_nodes[level_index].item_id is None:
                    single_sample = [item_id, level_nodes[level_index].val, 0, 0]
                else:
                    single_sample = [item_id, level_nodes[level_index].item_id, 1, 0]
                samples.append(single_sample)
        level_nodes = tmp
        k += 1
        j -= 1
    e = time.clock()
    print('time %f' % (e-s))
    samples = pd.DataFrame(samples, columns=['item_ID', 'node', 'is_leaf', 'label'])
    return samples

def map_generate(df):
    #生成map
    r_value = {}
    df = df.values
    for i in df:
        value = r_value.get(i[0])
        if value == None:
            r_value[i[0]] = [[i[1],i[2],i[3]]]
        else:
            r_value[i[0]].append([i[1], i[2], i[3]])
            r_value[i[0]] = r_value[i[0]]
    return r_value

def _single_node_sample_1(item_id, node, node_list):
    samples = []
    positive_info = []
    i = 0
    while node:
        if node.item_id is None:
            single_sample = [item_id, node.val, 0, 1]
            id = node.val
        else:
            single_sample = [item_id, node.item_id, 1, 1]
            id = node.item_id
        samples.append(single_sample)
        positive_info.append(id)
        node = node.parent
        i += 1
    #j从root节点到叶子节点的index k代表当前level
    j, k = i-2, 1
    #当前tree_list_map数据结构为[[(id,is_leaf)],[]]
    tree_depth = len(node_list)
    for i in range(1,tree_depth):
        tmp_map = node_list[i]
        if len(tmp_map) <= 2*k:
            index_list = range(len(tmp_map))
        else:
            index_list = random.sample(range(len(tmp_map)), k)
        if j == 0:
            index_list = random.sample(range(len(tmp_map)), k)
            remove_item = (positive_info[j], 1)
        else:
            remove_item = (positive_info[j], 0)
        sample_iter = []
        for level_index in index_list:
            single_sample = [item_id, tmp_map[level_index][0], tmp_map[level_index][1], 0]
            sample_iter.append(single_sample)

        if [item_id, remove_item[0], remove_item[1], 0] in sample_iter:
            sample_iter.remove([item_id, remove_item[0], remove_item[1], 0])
        samples.extend(sample_iter)
        k += 1
        j -= 1
        if(j < 0):break
    e = time.clock()
    return samples


def tree_generate_samples(items, leaf_dict, node_list):
    """Sample based on the constructed tree with multiprocess."""
    samples_total = []
    for item in items:
        node = leaf_dict[item]
        samples = _single_node_sample_1(item, node, node_list)
        samples_total.extend(samples)
        # total_samples = pd.concat(samples, ignore_index=True)
    samples = pd.DataFrame(samples_total, columns=['item_ID', 'node', 'is_leaf', 'label'])
    return samples
    # return total_samples


def _single_data_merge(data, tree_data):
    complete_data = None
    # tree_data ['item_ID', 'node', 'is_leaf', 'label']
    # data ['user_ID','timestamp','item','behaviors']
    item_ids = np.array(data.item_ID)
    # item_ids = item_ids[item_ids != -2]
    for item in item_ids:
        samples_tree_item = tree_data[tree_data.item_ID == item][['node', 'is_leaf', 'label']].reset_index(drop=True)
        size = samples_tree_item.shape[0]
        data_extend = pd.concat([data] * size, axis=1, ignore_index=True).T
        data_item = pd.concat([data_extend, samples_tree_item], axis=1)
        if complete_data is None:
            complete_data = data_item
        else:
            complete_data = pd.concat([complete_data, data_item], axis=0, ignore_index=True)
    return complete_data


def merge_samples(data, tree_map,mode):
    """combine the preprocessed samples and tree samples."""
    #生成样本数据 为了效率 树生成的物品index改成map结构
    train_size = data.shape[0]
    print('train_size %f' % train_size)
    r_value = []
    s = time.clock()
    #[user_ID,item_ID,behavior_num] ['node', 'is_leaf', 'label']
    for i in range(train_size):
        data_row = data.iloc[i]
        data_row_values = data_row.values
        item_list = data_row.item_ID
        for item in item_list:
            l_len = len(tree_map[item])
            tmp = np.append(l_len*[data_row_values],tree_map[item],axis=1)
            r_value.extend(tmp)
        if(i % 10000 == 0):
            o = time.clock()
            pd.DataFrame(r_value)\
                .to_csv('/home/dev/data/andrew.zhu/tdm/data_flow/%s.csv' % mode, mode='a',
                                         header=True)
            print('10000 time %f',(o-s))
            r_value = []
        # 18917

class DataInput:
  def __init__(self, data, batch_size):

    self.batch_size = batch_size
    self.data = data
    self.epoch_size = len(self.data) // self.batch_size
    if self.epoch_size * self.batch_size < len(self.data):
      self.epoch_size += 1
    self.i = 0

  def __iter__(self):
    return self

  def __next__(self):

    if self.i == self.epoch_size:
      raise StopIteration

    ts = self.data[self.i * self.batch_size : min((self.i+1) * self.batch_size,
                                                  len(self.data))]
    self.i += 1
    # (reviewerID, hist, albumId, label)
    i, y,is_leaf, sl =  [], [], [] , []
    for t in ts:
      i.append(t[3])
      y.append(t[5])
      sl.append(t[2])
      is_leaf.append(t[4])
    max_sl = max(sl)

    hist_i = np.zeros([len(ts), max_sl], np.int64)

    k = 0
    for t in ts:
      for l in range(len(t[1])):
        hist_i[k][l] = t[1][l]
      k += 1

    return self.i, (i, y,is_leaf, hist_i, sl)

class DataInputTest:
  def __init__(self, data, batch_size):

    self.batch_size = batch_size
    self.data = data
    self.epoch_size = len(self.data) // self.batch_size
    if self.epoch_size * self.batch_size < len(self.data):
      self.epoch_size += 1
    self.i = 0

  def __iter__(self):
    return self

  def __next__(self):

    if self.i == self.epoch_size:
      raise StopIteration

    ts = self.data[self.i * self.batch_size : min((self.i+1) * self.batch_size,
                                                  len(self.data))]
    self.i += 1
    # reviewerID, hist, label
    u, i, j, sl = [], [], [], []
    for t in ts:
      u.append(t[0])
      i.append(t[2][0])
      j.append(t[2][1])
      sl.append(len(t[1]))
    max_sl = max(sl)
    hist_i = np.zeros([len(ts), max_sl], np.int64)

    k = 0
    for t in ts:
      for l in range(len(t[1])):
        hist_i[k][l] = t[1][l]
      k += 1

    return self.i, (u, i, j, hist_i, sl)


def download(hdfs,local):
    # hdfs_path = ['/tmp/user/dev/andrew.zhu/vip/buy/*']
    #
    hdfs_train_paths = hdfs
    local_train_path = local
    client = HdfsClient()
    print('------------------------')
    print(hdfs_train_paths)
    print(local_train_path)
    print('------------------------')
    client.download(hdfs_train_paths,
                    local_train_path,
                    overwrite=True)

    print('----------------> get data finished  <-------------------' + str(local_train_path))

def main():
    hdfs_path = '/user/dev/andrew.zhu/tdm/PretrainData'
    local_path = '/home/dev/data/andrew.zhu/tdm/'
    # download(hdfs_path,local_path)
    #数据过滤了 >300 要修正
    data_process(local_path+"PretrainData")
    test_pickle()