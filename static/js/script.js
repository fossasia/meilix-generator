var customFileInputBox = document.querySelectorAll('.custom__file__input'); 

function addFileEventListeners(realInput, customTextBox, customButton) {

  customButton.addEventListener('click', e => {
    e.preventDefault();
    realInput.click();
    return false;
  });

  realInput.addEventListener("change", e => {
    if (realInput.value) {
      customTextBox.innerHTML = realInput.value.match(/[\/\\]([\w\d\s\.\-\(\)]+)$/)[1];
    } else {
      customTextBox.innerHTML = "";
    }
  });

}

customFileInputBox.forEach(el => {
  addFileEventListeners(el.children[0], el.children[1], el.children[2]);
});
