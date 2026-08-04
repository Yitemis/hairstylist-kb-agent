#!/bin/bash
# 强制所有缓存到 E 盘（避免 C 盘爆）
# 用法：source scripts/setup_env_paths.sh

# 临时文件
export TMPDIR=/e/cache/tmp
export TEMP=/e/cache/tmp
export TMP=/e/cache/tmp
mkdir -p $TMPDIR

# pip 缓存
export PIP_CACHE_DIR=/e/cache/pip
mkdir -p $PIP_CACHE_DIR

# Hugging Face (transformers / sentence-transformers)
export HF_HOME=/e/cache/huggingface
export HF_HUB_CACHE=/e/cache/huggingface/hub
export TRANSFORMERS_CACHE=/e/cache/huggingface/transformers
mkdir -p $HF_HOME $HF_HUB_CACHE $TRANSFORMERS_CACHE

# ModelScope (MinerU 用)
export MODELSCOPE_CACHE=/e/cache/modelscope
mkdir -p $MODELSCOPE_CACHE

# MinerU 配置
export MINERU_HOME=/e/mineru-data
export MINERU_MODEL_SOURCE=local
mkdir -p $MINERU_HOME

# Docker (WSL 内)
export DOCKER_CONFIG=/e/cache/docker
mkdir -p $DOCKER_CONFIG

echo "Env paths set to E drive:"
echo "  TMP/PIP/HF/ModelScope/MinerU all in E:"
echo "  TMPDIR=$TMPDIR"
echo "  PIP_CACHE_DIR=$PIP_CACHE_DIR"
echo "  HF_HOME=$HF_HOME"
echo "  MODELSCOPE_CACHE=$MODELSCOPE_CACHE"
echo "  MINERU_HOME=$MINERU_HOME"
