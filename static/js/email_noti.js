$(document).on('click', function() {
  $('.custom-menu-cont').toggleClass('hidden');
});

$('.custom-menubutton').on('click', function(e) {
  e.stopPropagation();
  $('.custom-menu-cont').toggleClass('hidden');
});
function disti()
{
	alert("This will be name of the distribution");
}
function hpage()
{
	alert("This will be the home page of the browser");
}
function sengine()
{
	alert("This will be the default search engine of the browser");
}
function pinstall()
{
	alert("packages will installed which you have checked");
}
