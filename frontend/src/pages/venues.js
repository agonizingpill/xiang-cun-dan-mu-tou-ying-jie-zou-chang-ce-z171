        import {workspace} from '../workspace.js';
        import {el} from '../dom.js';

        const page = {
  "title": "核对放映场地分路",
  "module": "场地配电和投影线",
  "caption": "场地配电和投影线",
  "detail": "场地合用时需验证计量协议一致，并有试投签字。",
  "path": "/venues",
  "columns": [
    {
      "name": "code",
      "label": "编号"
    },
    {
      "name": "protocol",
      "label": "计量协议"
    },
    {
      "name": "channels",
      "label": "可用分路"
    },
    {
      "name": "ready",
      "label": "已签场地"
    }
  ],
  "layout": "flip",
  "view": "grid",
  "actions": [
    {
      "name": "sign_venue",
      "label": "场地电表签认",
      "path": "/venues/sign-venue",
      "fields": [
        {
          "name": "venue",
          "label": "场地编号",
          "kind": "text",
          "initial": "HALL-C"
        },
        {
          "name": "receipt",
          "label": "电表协议验收号",
          "kind": "text",
          "initial": "MTR-030"
        }
      ],
      "help": "依据本地验收单确认场地。",
      "roles": [
        "reviewer"
      ],
      "success": "已写入"
    }
  ]
};

        export const {title} = page;
        export const key = "venues";
        export async function render(root, role) {
          await workspace(root, role, page);

        }
