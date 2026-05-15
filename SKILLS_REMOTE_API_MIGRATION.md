# Skills Remote API Migration

## 概述
将 Open WebUI 的技能管理系统从本地 SQLite 数据库迁移到远程 REST API（Hermes Agent API）。

## 修改内容

### 后端修改 (`backend/open_webui/routers/skills.py`)

#### 配置
- `HERMES_SKILLS_API_URL`: 远程 API 端点，默认为 `http://172.16.217.143:8642/v1/hermes/skills`
- `HERMES_SKILLS_API_KEY`: Bearer Token，默认为 `Asdf@1234`
- `HERMES_SKILLS_API_TIMEOUT`: 请求超时时间，默认为 30 秒

#### 新增辅助函数
1. **`_remote_skills_headers()`** - 构建包含 Bearer Token 的 HTTP 请求头
2. **`_normalize_remote_skill(item: dict)`** - 将远程 API 响应格式转换为本地 SkillModel 格式
   - 处理 `category` → `meta.tags` 的映射
   - 生成合成用户对象（id: 'hermes-skill-service'）
3. **`_fetch_remote_skills()`** - 调用远程 API 获取技能列表
   - 支持多种响应格式：直接列表、`{data: [...]}` 或 `{items: [...]}`

#### 修改的路由端点
1. **`GET /`** (GetSkills)
   - 从远程 API 获取所有技能
   - 返回 `list[SkillUserResponse]`

2. **`GET /list`** (GetSkillList)
   - 从远程 API 获取技能列表
   - 支持搜索（name/description/category）和分页
   - 返回 `SkillAccessListResponse`

3. **`GET /export`** (ExportSkills)
   - 从远程 API 获取技能用于导出
   - 返回 `list[SkillModel]`

4. **`GET /id/{id}`** (GetSkillById)
   - 从远程 API 按 ID 获取单个技能
   - 返回 `SkillAccessResponse`

5. **`POST /id/{id}/toggle`** (ToggleSkillById)
   - **新增**：调用远程 API 的 toggle 端点 (`{REMOTE_SKILLS_API_URL}/{id}/toggle`)
   - 支持启用/禁用技能
   - 返回 `SkillModel`

#### 禁用的操作
- `POST /create` (CreateNewSkill) - 已禁用
- `POST /id/{id}/update` (UpdateSkillById) - 已禁用
- `POST /id/{id}/access/update` (UpdateSkillAccessById) - 已禁用
- `DELETE /id/{id}/delete` (DeleteSkillById) - 已禁用

### 前端修改 (`src/lib/components/workspace/Skills.svelte`)

#### 移除的导入
- `createNewSkill` - 删除创建功能
- `deleteSkillById` - 删除删除功能

#### 移除的 UI 元素
1. **"New Skill" 创建按钮** - 已移除
2. **"Import" 导入按钮** - 已移除
3. **文件导入处理** - 已完全移除
4. **Delete 确认对话框** - 已移除
5. **Skills 菜单中的编辑/克隆/导出/删除选项** - 已简化

#### 保留的功能
- ✅ 显示远程技能列表（GET）
- ✅ 搜索技能
- ✅ 分页显示
- ✅ Toggle 技能启用/禁用状态

### 前端修改 (`src/lib/components/workspace/Skills/SkillMenu.svelte`)

#### 修改内容
- 菜单已禁用，仅保留注释说明
- 移除了所有操作选项（Edit、Clone、Export、Delete）
- 改为空组件

## 环境变量配置

```bash
# 可选，如不配置则使用默认值
export HERMES_SKILLS_API_URL=http://172.16.217.143:8642/v1/hermes/skills
export HERMES_SKILLS_API_KEY=Asdf@1234
export HERMES_SKILLS_API_TIMEOUT=30
```

## API 调用流程

### 获取技能列表
```
GET /api/v1/skills/list?query=&page=1
↓
调用 _fetch_remote_skills()
↓
请求 http://172.16.217.143:8642/v1/hermes/skills
(Header: Authorization: Bearer Asdf@1234)
↓
返回规范化的技能列表
```

### Toggle 技能状态
```
POST /api/v1/skills/id/{skillId}/toggle
↓
调用 httpx.post($REMOTE_SKILLS_API_URL/{skillId}/toggle)
(Header: Authorization: Bearer Asdf@1234)
↓
返回更新后的技能对象
```

## 已知限制

1. 远程 API 不支持创建/删除/编辑技能 - 这些操作已完全禁用
2. 只支持通过 toggle 来启用/禁用技能
3. 技能信息为只读（除了启用/禁用状态）
4. 访问控制（AccessGrants）目前在远程 API 调用中被忽略

## 迁移清单

- [x] 后端 API 端点全部转为远程调用
- [x] 实现远程响应格式转换
- [x] 实现 Toggle 功能的远程 API 调用
- [x] 前端移除创建/导入/删除功能
- [x] 前端移除编辑菜单选项
- [x] 保留搜索和分页功能
- [x] 保留 Toggle 按钮
- [x] 代码无语法错误

## 测试要点

1. 验证 Hermes API 连接（检查环境变量设置）
2. 测试技能列表加载
3. 测试搜索功能
4. 测试分页功能
5. 测试 Toggle 开关功能
6. 验证 UI 中不显示创建/编辑/删除按钮

