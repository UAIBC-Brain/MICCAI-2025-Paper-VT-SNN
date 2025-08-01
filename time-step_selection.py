import os
import sys
import time
import torch
import argparse
import datetime
import model_test
import torch.nn as nn
from torch.cuda import amp
from losses import Lossess
import torch.nn.functional as F
from monai.data import  DataLoader
from timm.models import create_model
# from utils.new_jsaon_data_utils import AgeData
from utils.new_jsaon_data_utils import AgeData
from torch.utils.tensorboard import SummaryWriter
from spikingjelly.clock_driven import neuron, functional, surrogate, layer

def main():

    parser = argparse.ArgumentParser(description="PyTorch Training")
    parser.add_argument("--logdir", default="test", type=str, help="directory to save the tensorboard logs")
    parser.add_argument("--epochs", default=400, type=int, help="number of training epochs")
    parser.add_argument('-device', default='cuda:0', help='device')
    parser.add_argument('-out-dir', type=str, default='./logs', help='root dir for saving logs and checkpoint')
    parser.add_argument("--in_channels", default=1, type=int, help="number of input channels")
    parser.add_argument('-amp', action='store_true', default=True, help='automatic mixed precision training')
    parser.add_argument('-cupy', action='store_true', default=True, help='use cupy backend')
    parser.add_argument("--dropout_path_rate", default=0.0, type=float, help="drop path rate")
    parser.add_argument("--use_checkpoint", action="store_true", help="use gradient checkpointing to save memory")
    parser.add_argument("--batch_size", default=8, type=int, help="number of batch size")
    parser.add_argument("--lr", default=0.01, type=float, help="learning rate")
    parser.add_argument("--decay", default=0.1, type=float, help="decay rate")
    parser.add_argument("--momentum", default=0.9, type=float, help="momentum")
    parser.add_argument("--lr_schedule", default="warmup_cosine", type=str)
    parser.add_argument('-resume', type=str, help='resume from the checkpoint path')
    parser.add_argument("--local_rank", type=int, default=0, help="local rank")
    parser.add_argument("--dist-url", default="env://", help="url used to set up distributed training")
    parser.add_argument('--distributed', action='store_true')
    parser.add_argument("--rank", default=0, type=int, help="node rank for distributed training")
    parser.add_argument("--clf_type", default='softplus', type=str, help="the clf_type contains softplus and exp")
    parser.add_argument("--kl_c", default=-1, type=int, help="kl's weight")
    parser.add_argument("--fisher_c", default=0.01, type=int, help="fisher_c's weight")
    parser.add_argument("--weight_decay", type=float, default=0, metavar="W",help="weight decay (default: 0.1)")
    parser.add_argument('-save-es', default=None,help='dir for saving a batch spikes encoded by the first {Conv2d-BatchNorm2d-IFNode}')
    parser.add_argument( "--model",default="spikformer",type=str,metavar="MODEL",help='Name of model to train (default: "spikformer")')
    parser.add_argument("--pooling-stat",default="1111",type=str,help="pooling layers in SPS moduls")
    parser.add_argument("--spike-mode",default="lif",type=str,help="")
    parser.add_argument("--layer",default=4,type=int,help="")
    parser.add_argument("--num-classes",type=int,default=2,metavar="N",help="number of label classes (Model default if None)")
    parser.add_argument("--T",type=int,default=4,metavar="N",help="")
    parser.add_argument( "--num-heads",type=int,default=8,metavar="N",help="")
    parser.add_argument("--opt",default="sgd",type=str,metavar="OPTIMIZER",help='Optimizer (default: "sgd")')
    parser.add_argument("--drop", type=float, default=0.1, metavar="PCT", help="Dropout rate (default: 0.)")
    parser.add_argument("--drop-path",type=float,default=0.2,metavar="PCT",help="Drop path rate (default: None)")
    parser.add_argument("--drop-block",type=float,default=None,metavar="PCT",help="Drop block rate (default: None)")
    args = parser.parse_args()
    print(args)

    # model = SFCN()
    model = create_model(
        args.model,
        img_size_d=128,  # 新增深度维度的尺寸
        img_size_h=128,
        img_size_w=128,
        patch_size=16,
        in_channels=1,
        num_classes=2,
        embed_dims=64,
        num_heads=8,
        mlp_ratios=4,
        qkv_bias=False,
        qk_scale=None,
        drop_rate=0.1,
        attn_drop_rate=0.0,
        drop_path_rate=0.1,
        norm_layer=nn.LayerNorm,
        depths=8,
        T = args.T,
        sr_ratios=1,
        pretrained=False,
        pretrained_cfg=None,
    )
    # print(model)

    model.to(args.device)
    pretrained_path = r'./logs/pjs_new/T4_8_sgd_lr0.01_c1_drop0.1_json7_0.01_amp_cupy/checkpoint_max.pth'
    # pretrained_path = r'./logs/pjs/T4_8_sgd_lr0.02_c1_drop0.1_3_0.01_amp_cupy/checkpoint_max.pth'
    #pretrained_path = r'./logs/jsb_spikeformer-unertrainty/T4_8_sgd_lr0.02_c1_drop0.1_jsb_100samples_0.01_amp_cupy/checkpoint_max.pth'
    # pretrained_path = r'./logs/ad_spikeformer-unertrainty/T4_8_sgd_lr0.01_c1_drop0.1_fishe_finnal_ad_test3_0.01_amp_cupy/checkpoint_max.pth'
    if os.path.exists(pretrained_path):
        checkpoint = torch.load(pretrained_path, map_location=args.device)
        if 'model' in checkpoint:
            model.load_state_dict(checkpoint['model'])
            print(f"成功加载预训练模型: {pretrained_path}")
        else:
            model.load_state_dict(checkpoint)  # 如果检查点直接保存的是模型状态字典
            print(f"加载旧格式的预训练模型: {pretrained_path}")
    else:
        raise FileNotFoundError(f"预训练模型未找到: {pretrained_path}")

    json_file = "./jsons/old/dataset_mat - spilt7.json"
    root_dir = "./dataset/data_round"
    # 创建测试数据集
    test_dataset = AgeData(json_file, root_dir, split='validation', transform=None)
    test_loader = DataLoader(test_dataset, batch_size=1, shuffle=False, num_workers=1)

    if args.resume:
        checkpoint = torch.load(args.resume, map_location='cpu')
        model.load_state_dict(checkpoint['model'])


    out_dir = os.path.join(args.out_dir,
                           f'T{args.T}_{args.batch_size}_{args.opt}_lr{args.lr}_c{args.in_channels}_drop{args.drop}_fishe and data_test{args.fisher_c}')

    if args.cupy:
        out_dir += '_cupy'

    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
        print(f'Mkdir {out_dir}.')
    writer = SummaryWriter(out_dir)
    with open(os.path.join(out_dir, 'args.txt'), 'w', encoding='utf-8') as args_txt:
        args_txt.write(str(args))
        args_txt.write('\n')
        args_txt.write(' '.join(sys.argv))

    model.eval()
    # model.set_visual_mode(True)  # 开启可视化模式
    viz_data = None  # 存储要可视化的数据
    test_acc = 0
    total_T = 0
    right_lable0 = 0
    right_lable1 = 0
    total_label0 = 0
    total_label1 = 0
    right_lable0 = 0
    right_lable1 = 0
    test_samples = 0
    noise_epsilon = 0  # 高斯噪声强度
    uniform_noise_epsilon = 0  # 均匀噪声强度
    test_total_loss = 0
    softplus_ = nn.Softplus()
    clf_type = args.clf_type

    # # 初始化计数器，用于统计不同 T 值的样本数量
    # t_counts = {1: 0, 2: 0, 3: 0, 4: 0}

    with torch.no_grad():
        model_pred_all = []
        for i_batch, batch_data in enumerate(test_loader):
            image = batch_data['image']
            image = image.unsqueeze(1)
            label = batch_data['label']
            label = torch.squeeze(label)
            label = label.long()
            # 将输入张量转换为 FloatTensor
            image = image.float()
            # poisson_noise = torch.poisson(image)
            # image = image + poisson_noise
            gaussian_noise = noise_epsilon * torch.randn_like(image)
            # 添加均匀噪声，这里假设均匀噪声范围是 [-uniform_noise_epsilon, uniform_noise_epsilon]
            uniform_noise = (torch.rand_like(image) * 2 - 1) * uniform_noise_epsilon
            # 叠加噪声到图像上
            image = (image + gaussian_noise + uniform_noise).to(args.device)
            label = label.to(args.device)
            label_onehot = F.one_hot(label, 2).float()
            out_fr = 0
            image = (image.unsqueeze(0)).repeat(args.T, 1, 1, 1, 1, 1)
            for t in range(args.T):
                image_x = image[t]
                out_fr += model(image_x)
                out_fr = out_fr / (t + 1)
                out_fr = out_fr.float()
                out_fr_1  = softplus_(out_fr) + 1.0
                model_pred_all.append(out_fr_1.to(args.device))
                id_alpha_pred_all = torch.cat(model_pred_all, dim=0)
                print('id_alpha_pred_all', id_alpha_pred_all)
                p = id_alpha_pred_all / torch.sum(id_alpha_pred_all, dim=-1, keepdim=True)
                scores = p.max(-1)[0].cpu().detach().numpy()
                mean_score = sum(scores) / len(scores)
                print("Mean score:", mean_score)
                # scores = scores[0]
                # print('scores',scores)
                model_pred_all.clear()
                if mean_score >= 0.85:
                    # if  (1-uncertaint7) >= 0.75 :
                    best_T = t + 1
                    break  # 满足条件，T循环
                else:
                    best_T = t + 1
            out_fr = out_fr / best_T
            if clf_type == "exp":
                evi_alp_ = torch.exp(out_fr) + 1.0
            elif clf_type == "softplus":
                evi_alp_ = softplus_(out_fr) + 1.0
            else:
                raise NotImplementedError
            test_samples += label.numel()
            test_acc += (evi_alp_.argmax(1) == label).float().sum().item()
            predicted_label = evi_alp_.argmax(1)
            right_lable0 += ((label == 0) & (predicted_label == label)).sum().item()
            right_lable1 += ((label == 1) & (predicted_label == label)).sum().item()
            total_label0 += (label == 0).sum().item()
            total_label1 += (label == 1).sum().item()
            total_T += best_T
            print('total_T', total_T)
            print('test_example', test_samples)
            # 更新对应 T 值的计数器
            # t_counts[best_T] += 1
            functional.reset_net(model)

        avg_T = total_T / 40

    test_time = time.time()
    test_total_loss /= test_samples
    test_acc /= test_samples
    # 计算 SEN（灵敏度）和 SPE（特异性）
    SEN = right_lable1 / total_label1 if total_label1 > 0 else 0  # 灵敏度 = TP / (TP + FN)
    SPE = right_lable0 / total_label0 if total_label0 > 0 else 0  # 特异性 = TN / (TN + FP)

    # 计算 F1 分数
    precision = right_lable1 / (right_lable1 + (total_label0 - right_lable0)) if (right_lable1 + (
            total_label0 - right_lable0)) > 0 else 0
    recall = SEN
    F1_score = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    # # 输出不同 T 值对应的样本数量
    # print("不同 T 值对应的样本数量统计：")
    # for t, count in t_counts.items():
    #     print(f"T = {t}: {count} 个样本")
    #
    # checkpoint = {
    #     'model': model.state_dict(),
    # }

    print(args)
    print(out_dir)
    print("avg_T", avg_T)
    print("right_label1:", right_lable1)
    print("right_label0:", right_lable0)
    print(f'test_acc ={test_acc: .4f}')
    print(f"SEN (Sensitivity): {SEN:.4f}")
    print(f"SPE (Specificity): {SPE:.4f}")
    print(f"F1 Score: {F1_score:.4f}")


if __name__ == '__main__':
    main()


# python -m testkk  -device cuda:0 -cupy -resume './logs\spikeformer-uncertainty\T4_8_sgd_lr0.02_c1_drop0.1_fishe_finnal_split1_0.01_amp_cupy/checkpoint_max.pth'
# python -m ood_single  -device cuda:0 -cupy -resume './logs\spikeformer-uncertainty\T4_8_sgd_lr0.02_c1_drop0.1_fishe_finnal_split1_0.01_amp_cupy/checkpoint_max.pth'