        import {workspace} from '../workspace.js';
        import {el} from '../dom.js';

        const page = {
  "title": "现场弹幕试投轨迹",
  "module": "试投节奏轨迹",
  "caption": "试投节奏轨迹",
  "detail": "保留实测拍点与总漂移。轨迹由现场领班核对后进入可匹配集合。",
  "path": "/cue_tracks",
  "columns": [
    {
      "name": "code",
      "label": "编号"
    },
    {
      "name": "venue",
      "label": "场地"
    },
    {
      "name": "timings",
      "label": "拍点序列"
    },
    {
      "name": "shift",
      "label": "总偏移秒"
    },
    {
      "name": "locked",
      "label": "模板已见证"
    }
  ],
  "layout": "stack",
  "view": "table",
  "actions": [
    {
      "name": "record_track",
      "label": "登记试投节奏",
      "path": "/cue_tracks/record-track",
      "fields": [
        {
          "name": "code",
          "label": "素材号",
          "kind": "text",
          "initial": "CUE-FINAL"
        },
        {
          "name": "venue",
          "label": "场地号",
          "kind": "text",
          "initial": "HALL-A"
        },
        {
          "name": "timings",
          "label": "序列",
          "kind": "json",
          "initial": [
            0.66,
            1.31,
            1.95,
            2.6,
            3.25,
            3.92
          ]
        },
        {
          "name": "shift",
          "label": "总偏移秒",
          "kind": "float",
          "initial": 0.21
        }
      ],
      "help": "现场录入已按拍点排序的时间序列。",
      "roles": [
        "operator",
        "reviewer"
      ],
      "success": "已写入"
    },
    {
      "name": "lock_track",
      "label": "确认试投记录",
      "path": "/cue_tracks/lock-track",
      "fields": [
        {
          "name": "track",
          "label": "试投素材",
          "kind": "text",
          "initial": "CUE-FINAL"
        }
      ],
      "help": "核对现场见证后锁定序列。",
      "roles": [
        "reviewer"
      ],
      "success": "已写入"
    }
  ]
};

        export const {title} = page;
        export const key = "cue_tracks";
        export async function render(root, role) {
          await workspace(root, role, page);

        }
