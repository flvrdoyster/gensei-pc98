/**
 * 피드백 수신 엔드포인트 (Google Apps Script 웹앱).
 * emulator/feedback.js 의 POST 를 구글 시트에 쌓고, 스크린샷은 Drive 에 저장 후 링크만 기록.
 *
 * - doGet 을 두지 않는 건 의도적 — 시트를 반환하는 doGet 이 있으면 URL 만 알면
 *   남의 제보를 읽을 수 있다. 쓰기 전용으로 유지할 것.
 * - 스크린샷을 Drive 로 빼는 이유: 시트 셀은 5만 자 제한이라 base64 가 안 들어간다.
 */

// 스크린샷을 담을 Drive 폴더 이름 (없으면 자동 생성)
var FOLDER_NAME = 'gensei-pc98 피드백 스크린샷';
var MAX_LEN = 2000;

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) return _ok();
    var d = JSON.parse(e.postData.contents);

    // 허니팟 — 봇이 채운 요청은 조용히 버린다 (성공처럼 응답해 재시도를 유도하지 않음)
    if (d.website) return _ok();

    var message = String(d.message || '').slice(0, MAX_LEN);
    if (!message.trim()) return _ok();

    var shotUrl = '';
    if (d.shot) {
      try {
        shotUrl = _saveShot(d.shot, d.game);
      } catch (err) {
        shotUrl = '(저장 실패: ' + err + ')';
      }
    }

    _append(SpreadsheetApp.getActiveSpreadsheet().getSheets()[0], [
      new Date(),
      String(d.category || ''),
      String(d.game || ''),
      String(d.version || ''),
      message,
      shotUrl,
      String(d.ua || '').slice(0, 500),
      String(d.url || '').slice(0, 500)
    ]);

    return _ok();
  } catch (err) {
    // 실패해도 내부 정보를 노출하지 않는다
    return ContentService.createTextOutput('error').setMimeType(ContentService.MimeType.TEXT);
  }
}

function _ok() {
  return ContentService.createTextOutput('ok').setMimeType(ContentService.MimeType.TEXT);
}

/**
 * 한 행 추가.
 *
 * appendRow 를 안 쓰는 이유: appendRow 는 "내용이 있는 마지막 행" 다음에 쓰는데,
 * 시트 아래쪽(예: 1000행 근처)에 눈에 안 띄는 잔여 내용이나 서식이 있으면
 * 1001행부터 쌓여서 기록이 안 되는 것처럼 보인다 (실제로 겪음).
 * A열(타임스탬프 — 정상 행이면 반드시 값이 있음)을 아래에서부터 훑어
 * 진짜 마지막 데이터 행을 찾고 그 다음 줄에 직접 쓴다.
 */
function _append(sheet, values) {
  sheet.getRange(_nextRow(sheet), 1, 1, values.length).setValues([values]);
}

function _nextRow(sheet) {
  var last = sheet.getLastRow();
  if (last < 1) return 1;
  var colA = sheet.getRange(1, 1, last, 1).getValues();
  for (var i = colA.length - 1; i >= 0; i--) {
    if (String(colA[i][0]).trim() !== '') return i + 2;
  }
  return 1;   // A열이 전부 비어 있으면 첫 줄부터
}

function _saveShot(dataUrl, game) {
  var b64 = String(dataUrl).replace(/^data:image\/\w+;base64,/, '');
  var bytes = Utilities.base64Decode(b64);
  var name = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyyMMdd-HHmmss') +
             '-' + (game || 'unknown') + '.png';
  var blob = Utilities.newBlob(bytes, 'image/png', name);

  var it = DriveApp.getFoldersByName(FOLDER_NAME);
  var folder = it.hasNext() ? it.next() : DriveApp.createFolder(FOLDER_NAME);
  // 공개 공유하지 않는다 — 소유자만 열람 (기본 권한 그대로 둠)
  return folder.createFile(blob).getUrl();
}
