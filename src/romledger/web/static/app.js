(function () {
  "use strict";

  document.documentElement.classList.add("js");

  function localizeTimes() {
    var formatter = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
    document.querySelectorAll("time[datetime]").forEach(function (element) {
      var date = new Date(element.getAttribute("datetime"));
      if (!isNaN(date)) {
        element.textContent = formatter.format(date);
      }
    });
  }

  function createRow(list, file) {
    var row = document.createElement("li");
    row.className = "upload";
    var name = document.createElement("span");
    name.className = "upload-name";
    name.textContent = file.name;
    var status = document.createElement("span");
    status.className = "muted";
    status.textContent = "Waiting";
    var bar = document.createElement("progress");
    bar.max = 100;
    bar.value = 0;
    bar.setAttribute("aria-label", "Upload progress for " + file.name);
    row.append(name, status, bar);
    list.append(row);
    return { status: status, bar: bar };
  }

  function send(url, file, row) {
    return new Promise(function (resolve) {
      var request = new XMLHttpRequest();
      var data = new FormData();
      data.append("files", file, file.name);
      request.open("POST", url);
      request.setRequestHeader("Accept", "application/json");
      request.upload.onprogress = function (event) {
        if (event.lengthComputable) {
          row.bar.value = Math.round((event.loaded / event.total) * 100);
          row.status.textContent = row.bar.value + "%";
        }
      };
      request.onload = function () {
        var ok = request.status === 200;
        row.bar.value = ok ? 100 : row.bar.value;
        row.status.textContent = ok ? "Done" : failure(request);
        row.status.className = ok ? "muted" : "upload-failed";
        resolve(ok);
      };
      request.onerror = function () {
        row.status.textContent = "Network error";
        row.status.className = "upload-failed";
        resolve(false);
      };
      request.send(data);
    });
  }

  function failure(request) {
    try {
      return JSON.parse(request.responseText).detail || "Failed";
    } catch (error) {
      return "Failed (" + request.status + ")";
    }
  }

  function setUpUploads(zone) {
    var form = zone.closest("form");
    var input = zone.querySelector("input[type=file]");
    var list = document.getElementById("upload-list");
    var busy = false;

    async function upload(files) {
      if (busy || !files.length) {
        return;
      }
      busy = true;
      var failed = false;
      for (var file of Array.from(files)) {
        var ok = await send(form.action, file, createRow(list, file));
        failed = failed || !ok;
      }
      busy = false;
      input.value = "";
      if (!failed) {
        window.location.assign(window.location.pathname + "?uploaded=" + files.length);
      }
    }

    input.addEventListener("change", function () {
      upload(Array.from(input.files));
    });
    ["dragenter", "dragover"].forEach(function (type) {
      zone.addEventListener(type, function (event) {
        event.preventDefault();
        zone.classList.add("is-dragover");
      });
    });
    ["dragleave", "drop"].forEach(function (type) {
      zone.addEventListener(type, function () {
        zone.classList.remove("is-dragover");
      });
    });
    zone.addEventListener("drop", function (event) {
      event.preventDefault();
      upload(Array.from(event.dataTransfer.files));
    });
  }

  localizeTimes();
  var zone = document.querySelector("[data-dropzone]");
  if (zone) {
    setUpUploads(zone);
  }
})();
