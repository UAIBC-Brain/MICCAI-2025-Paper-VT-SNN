# MICCAI-2025-Paper-VT-SNN
VT-SNN: Variable Time-step Spiking Neural Network Based on Uncertainty Measure and Its Application in Brain Disease Diagnosis

### Our codes are based on the following framework.

pytorch==1.13.0	

numpy==1.23.0

timm==0.6.12

cupy==13.3.0

spikingjelly==0.0.0.0.12

SimpleITK==2.4.0

json

sklearn

<p align="center">
<img src="https://github.com/ZK-Zhou/spikformer/blob/main/images/overview01.png">
</p>


data prepare: ImageNet with the following folder structure, you can extract imagenet by this [script](https://gist.github.com/BIGBALLON/8a71d225eff18d88e469e6ea9b39cef4).
```
│imagenet/
├──train/
│  ├── n01440764
│  │   ├── n01440764_10026.JPEG
│  │   ├── n01440764_10027.JPEG
│  │   ├── ......
│  ├── ......
├──val/
│  ├── n01440764
│  │   ├── ILSVRC2012_val_00000293.JPEG
│  │   ├── ILSVRC2012_val_00002138.JPEG
│  │   ├── ......
│  ├── ......
```


### Training  on ImageNet
Setting hyper-parameters in imagenet.yml

```
cd imagenet
python -m torch.distributed.launch --nproc_per_node=8 train.py
```

### Testing ImageNet Val data 
```
cd imagenet
python test.py
```

### Training  on cifar10
Setting hyper-parameters in cifar10.yml
```
cd cifar10
python train.py
```
### Training  on cifar10DVS
```
cd cifar10dvs
python train.py
```
