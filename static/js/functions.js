/*add all function script here*/

/*<----start loader script---->*/
$("nav").hide();
				$(document).ready(function(){
					$("nav").show();
			 $(".welcome").fadeOut("slow", function() { 
				 $(this).css({visibility: "hidden", opacity: 0});
	});
       });
/*<----loader script End---->*/

/*<----Drop down menu show hide---->*/
$(document).on("click", ".glyphicon-th", function () {
    document.getElementsByClassName("custom-menu-cont")[0].classList.toggle("hidden");
});
