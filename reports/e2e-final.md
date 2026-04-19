# E2E Triple-Provider Acceptance Report

Generated at: 2026-04-17 18:46:38
Backend: http://127.0.0.1:8000

## Projects

| Key | Provider | Project ID | Doc ID | Sections | Tasks | Quality | HighAmb | Build |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| api | api | `0976ae10-a2d5-41c8-8a91-49a44ba3e59a` | `2de224a5-9511-407e-a675-1daa02c190a3` | 10 | 35 |  89.5 | 0 | COMPLETE |
| claude | claude_code | `f5a6e0c9-9269-4f59-9fbc-1cdc6b000dbf` | `a2db67fd-e7c7-4868-b02a-fdc28d279a46` | 10 | None |   n/a | None | SKIPPED_SMOKE |
| cursor | cursor | `2baf08c1-3dad-4792-99e1-9e832e095c2d` | `62f7e853-2bfc-45f9-a724-ee01834e5b3d` | 39 | None |   n/a | None | SKIPPED_SMOKE |

## Reverse FS Comparison

| Provider | Doc ID | Sections | Flows | Quality |
| --- | --- | --- | --- | --- |
| api | `712a58bb-756e-4b50-b06c-0eb0b1f09386` | None | 0 | 100.0 |
| claude_code | `None` | None | None | n/a |
| cursor | `None` | None | None | n/a |

## Phase status

- `preflight` -> **ok**
- `project_api` -> **ok**
- `project_claude` -> **ok**
- `project_cursor` -> **ok**
- `reverse_upload` -> **ok**
- `reverse_api` -> **ok**
- `reverse_claude_code` -> **ok**
- `reverse_cursor` -> **ok**
- `mcp_matrix` -> **ok**
- `report` -> **ok**
- `cursor_ide_kickoff` -> **ok**
- `cursor_ide_verify` -> **ok**

## Endpoint coverage

Total endpoints hit: 173

- `GET /api/activity` x 1
- `GET /api/activity-log` x 1
- `GET /api/audit` x 1
- `GET /api/code/2fb84465-4982-43c2-acd0-01652b63ba59` x 1
- `GET /api/code/9ccd78dc-e167-4efb-a28e-8a73f90606b3` x 1
- `GET /api/duplicates` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/ambiguities` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/approval-status` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/audit-log` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/build-prompt` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/comments` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/contradictions` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/duplicates` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/edge-cases` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/export/docx` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/export/pdf` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/file-registry` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/post-build-check` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/pre-build-check` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/quality-score` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks` x 2
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/043431c6-874e-4fee-967a-8f2ea16948b2/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/043431c6-874e-4fee-967a-8f2ea16948b2/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/04760eef-f0fd-4ce1-bd2d-ffee8d06114a/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/04760eef-f0fd-4ce1-bd2d-ffee8d06114a/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/0738a3d5-2ca3-4aba-a6df-1acd7bf19e8e/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/0738a3d5-2ca3-4aba-a6df-1acd7bf19e8e/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/0d091f6b-0978-4a45-8224-39fd999cdfb2/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/0d091f6b-0978-4a45-8224-39fd999cdfb2/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/172daa66-438e-46d0-86b0-cc82b043c8a7/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/172daa66-438e-46d0-86b0-cc82b043c8a7/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/255a44f6-fb7c-4697-b2fc-40fda9055c35/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/255a44f6-fb7c-4697-b2fc-40fda9055c35/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/2768527e-c8cd-4f88-a195-f92e00b5de8c/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/2768527e-c8cd-4f88-a195-f92e00b5de8c/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/32fe152b-a884-4444-bcbb-8eba76d1d891/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/32fe152b-a884-4444-bcbb-8eba76d1d891/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/3c32b9e6-b533-46ae-963f-68d2547fb3b0/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/3c32b9e6-b533-46ae-963f-68d2547fb3b0/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/43819f78-8c27-40ec-9e81-96258f87a269/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/43819f78-8c27-40ec-9e81-96258f87a269/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/47dc56fd-7386-4bac-9b84-2484f47a2cd5/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/47dc56fd-7386-4bac-9b84-2484f47a2cd5/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/62ab8233-0239-440d-8f02-d2d96a422157/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/62ab8233-0239-440d-8f02-d2d96a422157/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/6fe868db-2c4b-4c5f-8ed1-d973609fc1c9/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/6fe868db-2c4b-4c5f-8ed1-d973609fc1c9/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/77744e17-1a64-42c3-b6f5-8b588882e964/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/77744e17-1a64-42c3-b6f5-8b588882e964/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/7cc3c2a2-64f3-49d1-8c9b-395feefb2617/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/7cc3c2a2-64f3-49d1-8c9b-395feefb2617/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/7d3da01b-3394-401c-ad8f-827374c0a900/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/7d3da01b-3394-401c-ad8f-827374c0a900/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/80bcb3d2-6070-46c1-90ac-5da3ae7b4112/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/80bcb3d2-6070-46c1-90ac-5da3ae7b4112/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/82af2676-0a69-48b5-951a-55f0ddc624ed/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/82af2676-0a69-48b5-951a-55f0ddc624ed/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/8711dbfb-e9d6-4555-9361-510a086d0745/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/8711dbfb-e9d6-4555-9361-510a086d0745/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/87e6f74a-8e21-44f7-a6f5-3486d6d7aac8/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/87e6f74a-8e21-44f7-a6f5-3486d6d7aac8/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/89aec12b-91b1-4c9d-94fe-fdf6717fb6bf/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/89aec12b-91b1-4c9d-94fe-fdf6717fb6bf/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/a44a876e-fb5f-48da-890f-f4c23d7935dd/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/a44a876e-fb5f-48da-890f-f4c23d7935dd/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/b3560288-b1da-4294-b852-cba50e138dff/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/b3560288-b1da-4294-b852-cba50e138dff/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/b39278d9-d1c6-423d-ae64-d5766970a4ae/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/b39278d9-d1c6-423d-ae64-d5766970a4ae/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/b762fad7-95f1-4374-8ec5-d93bf52aa908/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/b762fad7-95f1-4374-8ec5-d93bf52aa908/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/b88e89b5-5177-4930-a4e2-80607ff3002b/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/b88e89b5-5177-4930-a4e2-80607ff3002b/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/bb63cbe9-dbae-4c93-8cc0-a3939d4e097e/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/bb63cbe9-dbae-4c93-8cc0-a3939d4e097e/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/bbbfdc10-641a-4710-94e4-1e0910421d26/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/bbbfdc10-641a-4710-94e4-1e0910421d26/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/be00c86f-e35c-43f6-8a89-1bb5ff773f4f/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/be00c86f-e35c-43f6-8a89-1bb5ff773f4f/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/d4299645-b802-4cb9-86f6-c68838f046ba/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/d4299645-b802-4cb9-86f6-c68838f046ba/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/d8d1a74d-54e8-46d0-b1aa-7b986eb9cb65/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/d8d1a74d-54e8-46d0-b1aa-7b986eb9cb65/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/dcf6ee72-6be4-449d-8500-12a783d7e27e/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/dcf6ee72-6be4-449d-8500-12a783d7e27e/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/dd4a3908-9b67-4ac9-a1b9-ae2064d8168a/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/dd4a3908-9b67-4ac9-a1b9-ae2064d8168a/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/dependency-graph` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/e29ab00b-e57f-45f7-96c4-43590d5ad122/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/e29ab00b-e57f-45f7-96c4-43590d5ad122/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/e4e671f5-7dec-482e-a281-0e7801dacac4/context` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/e4e671f5-7dec-482e-a281-0e7801dacac4/verify` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/test-cases` x 1
- `GET /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/traceability` x 1
- `GET /api/fs/62f7e853-2bfc-45f9-a724-ee01834e5b3d/file-registry` x 1
- `GET /api/fs/62f7e853-2bfc-45f9-a724-ee01834e5b3d/post-build-check` x 1
- `GET /api/fs/712a58bb-756e-4b50-b06c-0eb0b1f09386/quality-score` x 1
- `GET /api/fs/None/quality-score` x 1
- `GET /api/fs/a2db67fd-e7c7-4868-b02a-fdc28d279a46` x 5
- `GET /api/fs/a2db67fd-e7c7-4868-b02a-fdc28d279a46/analysis-progress` x 2
- `GET /api/idea/health` x 1
- `GET /api/library` x 1
- `GET /api/library/search?q=todo` x 1
- `GET /api/mcp/sessions/37a6eece-3681-4b00-8566-f99da451af92/events` x 1
- `GET /api/mcp/sessions/7304cee4-1a7e-4fa2-8bab-4013e22f1d59/events` x 1
- `GET /api/orchestration/capabilities` x 1
- `GET /api/orchestration/mcp-config` x 2
- `GET /api/orchestration/providers` x 2
- `GET /api/projects` x 2
- `GET /health` x 2
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/build-state` x 2
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/comments/ea9fbd98-cd8b-482c-b939-55147f291c27/resolve` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/043431c6-874e-4fee-967a-8f2ea16948b2` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/04760eef-f0fd-4ce1-bd2d-ffee8d06114a` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/0738a3d5-2ca3-4aba-a6df-1acd7bf19e8e` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/0d091f6b-0978-4a45-8224-39fd999cdfb2` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/172daa66-438e-46d0-86b0-cc82b043c8a7` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/255a44f6-fb7c-4697-b2fc-40fda9055c35` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/2768527e-c8cd-4f88-a195-f92e00b5de8c` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/32fe152b-a884-4444-bcbb-8eba76d1d891` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/3c32b9e6-b533-46ae-963f-68d2547fb3b0` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/43819f78-8c27-40ec-9e81-96258f87a269` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/47dc56fd-7386-4bac-9b84-2484f47a2cd5` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/62ab8233-0239-440d-8f02-d2d96a422157` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/6fe868db-2c4b-4c5f-8ed1-d973609fc1c9` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/77744e17-1a64-42c3-b6f5-8b588882e964` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/7cc3c2a2-64f3-49d1-8c9b-395feefb2617` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/7d3da01b-3394-401c-ad8f-827374c0a900` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/80bcb3d2-6070-46c1-90ac-5da3ae7b4112` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/82af2676-0a69-48b5-951a-55f0ddc624ed` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/8711dbfb-e9d6-4555-9361-510a086d0745` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/87e6f74a-8e21-44f7-a6f5-3486d6d7aac8` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/89aec12b-91b1-4c9d-94fe-fdf6717fb6bf` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/a44a876e-fb5f-48da-890f-f4c23d7935dd` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/b3560288-b1da-4294-b852-cba50e138dff` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/b39278d9-d1c6-423d-ae64-d5766970a4ae` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/b762fad7-95f1-4374-8ec5-d93bf52aa908` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/b88e89b5-5177-4930-a4e2-80607ff3002b` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/bb63cbe9-dbae-4c93-8cc0-a3939d4e097e` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/bbbfdc10-641a-4710-94e4-1e0910421d26` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/be00c86f-e35c-43f6-8a89-1bb5ff773f4f` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/d4299645-b802-4cb9-86f6-c68838f046ba` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/d8d1a74d-54e8-46d0-b1aa-7b986eb9cb65` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/dcf6ee72-6be4-449d-8500-12a783d7e27e` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/dd4a3908-9b67-4ac9-a1b9-ae2064d8168a` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/e29ab00b-e57f-45f7-96c4-43590d5ad122` x 1
- `PATCH /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/tasks/e4e671f5-7dec-482e-a281-0e7801dacac4` x 1
- `POST /api/code/2fb84465-4982-43c2-acd0-01652b63ba59/generate-fs` x 3
- `POST /api/code/9ccd78dc-e167-4efb-a28e-8a73f90606b3/generate-fs` x 2
- `POST /api/code/upload` x 2
- `POST /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/analyze` x 1
- `POST /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/approve` x 1
- `POST /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/build-state` x 1
- `POST /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/export/confluence` x 1
- `POST /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/export/jira` x 1
- `POST /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/file-registry` x 72
- `POST /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/sections/0/comments` x 1
- `POST /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/snapshots` x 1
- `POST /api/fs/2de224a5-9511-407e-a675-1daa02c190a3/submit-for-approval` x 1
- `POST /api/fs/62f7e853-2bfc-45f9-a724-ee01834e5b3d/analyze` x 1
- `POST /api/fs/a2db67fd-e7c7-4868-b02a-fdc28d279a46/analyze` x 5
- `POST /api/fs/a2db67fd-e7c7-4868-b02a-fdc28d279a46/cancel-analysis` x 2
- `POST /api/idea/generate` x 2
- `POST /api/idea/guided` x 2
- `POST /api/mcp/sessions` x 3
- `POST /api/mcp/sessions/37a6eece-3681-4b00-8566-f99da451af92/events` x 4
- `POST /api/mcp/sessions/7304cee4-1a7e-4fa2-8bab-4013e22f1d59/events` x 4
- `POST /api/projects` x 3
- `POST /api/projects/0976ae10-a2d5-41c8-8a91-49a44ba3e59a/documents/2de224a5-9511-407e-a675-1daa02c190a3` x 1
- `POST /api/projects/2baf08c1-3dad-4792-99e1-9e832e095c2d/documents/62f7e853-2bfc-45f9-a724-ee01834e5b3d` x 1
- `POST /api/projects/f5a6e0c9-9269-4f59-9fbc-1cdc6b000dbf/documents/a2db67fd-e7c7-4868-b02a-fdc28d279a46` x 1
- `PUT /api/orchestration/config` x 11

## Repair events

- `analyze:claude` attempt=1 error=`ReadTimeout: `
- `analyze:claude` attempt=2 error=`ReadTimeout: `
- `analyze:claude` attempt=3 error=`ReadTimeout: `
