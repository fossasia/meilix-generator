/* global $ */

  var customMenuButton = $('.custom-menubutton');
  var menuContent = $('.custom-menu-cont');
  var fontAwesomeIcom=$('.glyphicon-th');

  customMenuButton.click(function() {
    menuContent.toggleClass("hidden");
    $(this).toggleClass('custom-menubutton-color');
  });

  $('.custom-menu-item').click(function () {
     menuContent.addClass('hidden');
     customMenuButton.removeClass('custom-menubutton-color');
  });

  $(document).mouseup(function(e) {
    // if the target of the click is not the button,
    // the container, or descendants of the container
    if (!$(e.target).is(customMenuButton) && !$(e.target).is(menuContent) && menuContent.has(e.target).length === 0 && !$(e.target).is(fontAwesomeIcom)) {
      menuContent.addClass("hidden");
      customMenuButton.removeClass('custom-menubutton-color');
    }
  });
