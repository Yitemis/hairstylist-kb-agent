# 【临时文档·后续删除】数据库表设计

> ⚠️ 临时文档，功能落地后可删除
> 创建日期：2026-07-30
> 数据库：SQLite（开发阶段）→ MySQL（生产阶段）
> ORM：SQLAlchemy

---

## users（C 端用户表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| phone | VARCHAR(20) UNIQUE | 手机号（登录用） |
| password_hash | VARCHAR(255) | 密码哈希（bcrypt） |
| name | VARCHAR(50) | 姓名/昵称 |
| avatar | VARCHAR(500) | 头像 URL |
| role | VARCHAR(20) | 固定 'user' |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

---

## staffs（B 端店家/员工表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| phone | VARCHAR(20) UNIQUE | 手机号（登录用） |
| password_hash | VARCHAR(255) | 密码哈希 |
| name | VARCHAR(50) | 姓名 |
| avatar | VARCHAR(500) | 头像 URL |
| role | VARCHAR(20) | admin / worker |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

---

## stylists（发型师表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| name | VARCHAR(50) | 姓名 |
| avatar | VARCHAR(500) | 头像 |
| specialties | TEXT | 擅长领域（JSON 数组） |
| description | TEXT | 简介 |
| is_active | BOOLEAN | 是否在职 |
| created_at | DATETIME | 创建时间 |

---

## services（服务项目表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| name | VARCHAR(100) | 项目名称 |
| category | VARCHAR(50) | 分类：烫发/染发/护理/剪发/造型 |
| duration_minutes | INTEGER | 服务时长（分钟） |
| price | DECIMAL(10,2) | 价格 |
| description | TEXT | 描述 |
| is_active | BOOLEAN | 是否上架 |

---

## orders（订单表，核心）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| order_no | VARCHAR(32) UNIQUE | 订单号（自动生成） |
| user_id | INTEGER FK | 用户 ID |
| stylist_id | INTEGER FK | 发型师 ID（可空，下单时选） |
| service_type | VARCHAR(100) | 服务项目 |
| service_details | TEXT | 服务细节描述 |
| appointment_date | DATE | 预约日期 |
| appointment_time | TIME | 预约时间 |
| customer_phone | VARCHAR(20) | 联系电话 |
| customer_name | VARCHAR(50) | 联系人姓名 |
| address | VARCHAR(500) | 店铺地址 |
| note | TEXT | 用户备注 |
| status | VARCHAR(20) | pending/confirmed/completed/cancelled |
| conversation_history | TEXT | 完整对话历史（JSON） |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

---

## 索引建议

- orders: user_id, status, appointment_date
- users/staffs: phone (唯一索引)
