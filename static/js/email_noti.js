$(document).on('click', function() {
  $('.custom-menu-cont').toggleClass('hidden');
});

$('.custom-menubutton').on('click', function(e) {
  e.stopPropagation();
  $('.custom-menu-cont').toggleClass('hidden');
});
function noti()
{
	alert("Email is used to mail user the link to the build ISO");
}
