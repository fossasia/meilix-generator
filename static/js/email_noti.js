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
  alert("This will install the packages which you have check");
}
$(document).on("click", ".glyphicon-th", function () {
    document.getElementsByClassName("custom-menu-cont")[0].classList.toggle("hidden");
});